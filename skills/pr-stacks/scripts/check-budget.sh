#!/usr/bin/env bash
#
# count the authored words in a drafted message and judge them against the
# budget for its mode and length band.
#
# the skill's central rule used to be "count before sending", which asks a
# language model to do arithmetic on its own prose — the least reliable way to
# enforce the one constraint the whole skill exists to hold. this does it in
# code instead: same input, same number, every time.
#
# what counts as INFORMATIONAL (stripped, free):
#   - urls
#   - the fact line: `• *repo#123* · +12/-3, 4 files · ready · green · approved`
#   - the header line: `<emoji> *TICKET-1 — title* · N PRs`
#   - bare metadata lines (sizes, states, positions)
# everything left is AUTHORED and is what gets counted.
#
# the split is heuristic by necessity — it reads a message, not a data
# structure. it is deliberately biased to OVER-count: a fact line that slips
# through inflates the total and makes the gate stricter, never looser.
#
set -euo pipefail

usage() {
  cat <<'EOF'
usage: check-budget.sh --file DRAFT [--mode digest|split|nudge|urgent]
                       [--length short|medium|long]

count authored words in a drafted message and compare against its budget.
exits 0 when inside budget, 1 when over. prints the count either way.

options:
  --file FILE      the drafted message (required)
  --mode MODE      default: digest
  --length BAND    default: medium (ignored for nudge and urgent)
  -h, --help
EOF
}

file=""
mode="digest"
length="medium"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file) file="$2"; shift 2 ;;
    --mode) mode="$2"; shift 2 ;;
    --length) length="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -n "$file" ]] || { echo "error: --file is required" >&2; usage >&2; exit 1; }
[[ -f "$file" ]] || { echo "error: no such file: $file" >&2; exit 1; }

case "$mode" in digest|split|nudge|urgent) ;; *)
  echo "error: --mode must be digest, split, nudge or urgent" >&2; exit 1 ;;
esac
case "$length" in short|medium|long) ;; *)
  echo "error: --length must be short, medium or long" >&2; exit 1 ;;
esac

# the connective-prose budget, before line items are added back
case "$mode" in
  digest)
    case "$length" in
      short)  budget=40 ;;
      medium) budget=60 ;;
      long)   budget=100 ;;
    esac
    ;;
  split)  budget=15 ;;   # plus its one line item, added below
  nudge)  budget=60 ;;
  urgent) budget=80 ;;
esac

# per-line-item bands, used to report whether each description sits in range
case "$length" in
  short)  item_lo=10; item_hi=25 ;;
  medium) item_lo=25; item_hi=50 ;;
  long)   item_lo=50; item_hi=90 ;;
esac
# a nudge chases; its line items are always short whatever the flag said
if [[ "$mode" == "nudge" ]]; then item_lo=10; item_hi=25; fi

# shellcheck disable=SC2016  # backticks are literal here, not command substitution
authored=$(
  sed -E \
    -e 's#https?://[^[:space:]]+##g' \
    -e '/^[[:space:]]*[•*-]?[[:space:]]*\*[^*]+\*[[:space:]]*·/d' \
    -e '/^[[:space:]]*[^[:alpha:]]*\*[^*]+—[^*]+\*[[:space:]]*·/d' \
    -e '/^[[:space:]]*[0-9]+ of [0-9]+ in the /d' \
    -e '/^[[:space:]]*\+[0-9]+\/-[0-9]+ /d' \
    -e '/^[[:space:]]*\*(Stacks|Waiting on review|Mergeable now)\*/d' \
    -e 's/`[^`]*`//g' \
    "$file"
)

words=$(printf '%s' "$authored" | tr -s '[:space:]' '\n' | grep -c '[[:alnum:]]' || true)

# line items are the indented prose blocks under a fact line, counted separately
# so a long description does not eat the connective budget or vice versa. a
# blank line ends an item.
item_counts=$(
  awk '
    /^[[:space:]]*[•*-]?[[:space:]]*\*[^*]+\*[[:space:]]*·/ {
      if (n > 0) print n
      n = 0; initem = 1; next
    }
    /^[[:space:]]*$/ { if (n > 0) print n; n = 0; initem = 0; next }
    initem {
      gsub(/https?:\/\/[^[:space:]]+/, "")
      n += NF
    }
    END { if (n > 0) print n }
  ' "$file"
)

# line items were counted inside the total; take them back out so the connective
# figure is what the digest budget actually governs.
item_total=0
while IFS= read -r c; do
  [[ -n "$c" ]] && item_total=$(( item_total + c ))
done <<< "$item_counts"

connective=$(( words - item_total ))
(( connective < 0 )) && connective=0

# a split message is one line item plus its framing
if [[ "$mode" == "split" ]]; then
  budget=$(( budget + item_hi ))
  connective=$words
fi

echo "mode=$mode length=$length"
echo "connective words: $connective   (budget $budget)"
echo "line items: ${item_counts//$'\n'/, }   (band ${item_lo}-${item_hi} each)"

status=0

if (( connective > budget )); then
  echo "OVER by $(( connective - budget )). Delete a sentence; do not compress a fact."
  status=1
else
  echo "within budget ($(( budget - connective )) to spare)"
fi

# under the floor is a finding, not a failure: a line item that says everything
# briefly stays brief. over the ceiling is the one that needs cutting.
while IFS= read -r c; do
  [[ -n "$c" ]] || continue
  if (( c > item_hi )); then
    echo "line item at $c words exceeds the ${length} ceiling of ${item_hi}"
    status=1
  elif (( c < item_lo )); then
    echo "note: line item at $c words is under the ${item_lo}-word floor — fine if it says everything, padding is not the fix"
  fi
done <<< "$item_counts"

exit $status

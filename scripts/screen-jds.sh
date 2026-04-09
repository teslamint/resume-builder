#!/bin/bash
set -e

cd "$(dirname "$0")/.."

check_deps() {
    local missing=()
    command -v python3 &>/dev/null || missing+=(python3)
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Error: Missing dependencies: ${missing[*]}" >&2
        exit 1
    fi
    if ! command -v claude &>/dev/null; then
        echo "Warning: 'claude' not found in PATH. LLM screening will fail (fallback to 지원 보류)." >&2
    fi
}

usage() {
    cat <<'EOF'
Usage: scripts/screen-jds.sh [OPTIONS]

Batch-screen unprocessed JD files using the existing Python screening pipeline.

Options:
  --dry-run     Preview screening without writing files or moving JDs
  --timeout N   LLM timeout in seconds (default: 120)
  -h, --help    Show this help message
EOF
    exit 0
}

DRY_RUN=false
TIMEOUT=120

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true; shift ;;
        --timeout)
            if [[ -z "${2:-}" ]]; then
                echo "Error: --timeout requires a value" >&2
                exit 1
            fi
            TIMEOUT="$2"; shift 2 ;;
        -h|--help)  usage ;;
        *)
            echo "Unknown option: $1" >&2
            usage ;;
    esac
done

check_deps

UNPROCESSED_DIR="private/job_postings/unprocessed"
SCREENING_DIR="private/jd_analysis/screening"

if [[ ! -d "$UNPROCESSED_DIR" ]]; then
    echo "No unprocessed directory found: $UNPROCESSED_DIR" >&2
    exit 1
fi

mapfile -t jd_files < <(find "$UNPROCESSED_DIR" -maxdepth 1 -name "*.md" -type f | sort)

if [[ ${#jd_files[@]} -eq 0 ]]; then
    echo "No .md files found in $UNPROCESSED_DIR"
    exit 0
fi

echo "Found ${#jd_files[@]} JD file(s) to process"
echo "Dry run: $DRY_RUN | Timeout: ${TIMEOUT}s"
echo "=========================================="

total=0
screened=0
already=0
errors=0

for jd_file in "${jd_files[@]}"; do
    total=$((total + 1))
    filename=$(basename "$jd_file")

    if [[ -f "$SCREENING_DIR/$filename" ]]; then
        echo "[$total/${#jd_files[@]}] SKIP (already screened): $filename"
        already=$((already + 1))
        continue
    fi

    echo "[$total/${#jd_files[@]}] Screening: $filename"

    dry_run_py="False"
    [[ "$DRY_RUN" == "true" ]] && dry_run_py="True"

    result=$(python3 -c "
import sys, json
sys.path.insert(0, '.')
from templates.jd.auto_company import _find_existing_company_file, _extract_company_name_from_jd
from templates.jd.auto_screening import run_screening
from templates.jd.pipeline import classify_file
from pathlib import Path

jd_path = Path(sys.argv[1])
dry_run = sys.argv[2] == 'True'
timeout = int(sys.argv[3])

company = _extract_company_name_from_jd(jd_path)
company_file = _find_existing_company_file(company) if company else None

sr = run_screening(jd_path, company_file, llm_timeout=timeout, dry_run=dry_run)

cr = classify_file(jd_path, dry_run=dry_run)

print(json.dumps({
    'verdict': sr.verdict,
    'provider': sr.provider,
    'used_fallback': sr.used_fallback,
    'screening_path': str(sr.screening_path),
    'classify': cr.message if hasattr(cr, 'message') else '',
    'company': company or 'unknown',
    'company_file': str(company_file) if company_file else '',
}))
" "$jd_file" "$dry_run_py" "$TIMEOUT" 2>&1) || {
        echo "  ERROR: screening failed for $filename"
        errors=$((errors + 1))
        continue
    }

    verdict=$(echo "$result" | tail -1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('verdict','?'))" 2>/dev/null) || verdict="?"
    provider=$(echo "$result" | tail -1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('provider','?'))" 2>/dev/null) || provider="?"
    company=$(echo "$result" | tail -1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('company',''))" 2>/dev/null) || company=""
    fallback=$(echo "$result" | tail -1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('used_fallback',False))" 2>/dev/null) || fallback=""

    echo "  Company: $company"
    echo "  Verdict: $verdict (via $provider)"
    [[ "$fallback" == "True" ]] && echo "  WARNING: Used fallback (LLM failed)"

    screened=$((screened + 1))
done

echo ""
echo "=========================================="
echo "Screening complete"
echo "  Total files:      $total"
echo "  Screened:         $screened"
echo "  Already screened: $already"
echo "  Errors:           $errors"
echo "=========================================="

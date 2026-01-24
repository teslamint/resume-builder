#!/bin/bash
set -e

cd "$(dirname "$0")"
mkdir -p build

check_deps() {
    local missing=()
    command -v python3 &>/dev/null || missing+=(python3)
    command -v pandoc &>/dev/null || missing+=(pandoc)
    command -v weasyprint &>/dev/null || missing+=(weasyprint)

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Error: Missing dependencies: ${missing[*]}" >&2
        exit 1
    fi
}

build_full() {
    local variant=$1
    local suffix=${2:-}
    local build_target=${3:-}
    local example_opt=${4:-}
    local output_name="build/resume-${variant}${suffix}"
    if [[ -n "$example_opt" ]]; then
        output_name="build/resume-example${suffix}"
    fi
    local css_path="$(pwd)/templates/themes/default/style.css"
    # Use target-specific style if exists
    if [[ -n "$build_target" && -f "overrides/${build_target}/style.css" ]]; then
        css_path="$(pwd)/overrides/${build_target}/style.css"
    fi
    echo "Building full resume (${variant}${suffix})..."
    python3 templates/resume_builder.py --variant "${variant}" ${build_target:+--target "$build_target"} ${example_opt} > "${output_name}.md"
    python3 templates/resume_builder.py --variant "${variant}" ${build_target:+--target "$build_target"} ${example_opt} --format pdf > "${output_name}-pdf.md"
    pandoc "${output_name}-pdf.md" -o "${output_name}.html" --standalone --css="${css_path}"
    weasyprint "${output_name}.html" "${output_name}.pdf"
    rm "${output_name}-pdf.md"
    pandoc "${output_name}.md" -t plain -o "${output_name}-remember.txt"
    echo "Generated: ${output_name}.pdf, ${output_name}-remember.txt"
}

build_short() {
    local variant=$1
    local build_target=${2:-}
    local example_opt=${3:-}
    local output_name="build/resume-${variant}-short"
    if [[ -n "$example_opt" ]]; then
        output_name="build/resume-example-short"
    fi
    local css_path="$(pwd)/templates/themes/default/style-short.css"
    echo "Building short resume (${variant})..."
    python3 templates/resume_builder.py --variant "${variant}" ${build_target:+--target "$build_target"} ${example_opt} --short > "${output_name}.md"
    python3 templates/resume_builder.py --variant "${variant}" ${build_target:+--target "$build_target"} ${example_opt} --short --format pdf > "${output_name}-pdf.md"
    pandoc "${output_name}-pdf.md" -o "${output_name}.html" --standalone --css="${css_path}"
    weasyprint "${output_name}.html" "${output_name}.pdf"
    rm "${output_name}-pdf.md"
    echo "Generated: ${output_name}.pdf"
}

build_wanted() {
    local variant=$1
    local build_target=${2:-}
    local example_opt=${3:-}
    local output_name="build/resume-${variant}-wanted.txt"
    if [[ -n "$example_opt" ]]; then
        output_name="build/resume-example-wanted.txt"
    fi
    echo "Building wanted resume (${variant})..."
    python3 templates/resume_builder.py --variant "${variant}" ${build_target:+--target "$build_target"} ${example_opt} --format wanted > "${output_name}"
    echo "Generated: ${output_name}"
}

build_base() {
    echo "Building base resume (job)..."
    build_full "job" "-base"
}

generate_notes() {
    local target=${1:-TBD}
    local clean_flag=${2:-}
    local suffix=${3:-}
    local current_file="build/resume-job${suffix}.md"
    if [[ -f "build/resume-job-base.md" ]]; then
        echo "Generating notes..."
        python3 templates/generate_notes.py \
            --base "build/resume-job-base.md" \
            --current "$current_file" \
            --target "$target" \
            $clean_flag
    else
        echo "Warning: build/resume-job-base.md not found. Run './build.sh job base' first to enable notes."
    fi
}

usage() {
    echo "Usage: $0 <public|job|example> [full|short|wanted|base|all] [options]" >&2
    echo "" >&2
    echo "Variants:" >&2
    echo "  public  - Senior profile, full company details, certificates" >&2
    echo "  job     - Practical profile, summarized old companies" >&2
    echo "  example - Demo with example data (for public repo)" >&2
    echo "" >&2
    echo "Formats:" >&2
    echo "  full    - Build full resume only" >&2
    echo "  short   - Build 1-page resume only" >&2
    echo "  wanted  - Build Wanted site format" >&2
    echo "  base    - Build base resume for diff (job only)" >&2
    echo "  all     - Build all formats (default)" >&2
    echo "" >&2
    echo "Options (job full only):" >&2
    echo "  --target <name>  - Target company/job posting name for notes" >&2
    echo "  --clean          - Overwrite notes file instead of append" >&2
    exit 1
}

check_deps

if [[ $# -lt 1 ]]; then
    usage
fi

variant=$1
shift

example_flag=""
if [[ "$variant" == "example" ]]; then
    example_flag="--example"
    variant="public"  # Use public variant with example data
fi

if [[ "$variant" != "public" && "$variant" != "job" ]]; then
    echo "Error: Invalid variant '$variant'. Use 'public', 'job', or 'example'." >&2
    usage
fi

format=${1:-all}
shift || true

target=""
clean_flag=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)
            target="$2"
            shift 2
            ;;
        --clean)
            clean_flag="--clean"
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

target_suffix=""
[[ -n "$target" ]] && target_suffix="-${target}"

case "$format" in
    full)
        build_full "$variant" "$target_suffix" "$target" "$example_flag"
        if [[ "$variant" == "job" && -z "$example_flag" ]]; then
            generate_notes "$target" "$clean_flag" "$target_suffix"
        fi
        ;;
    short)
        build_short "$variant" "$target" "$example_flag"
        ;;
    wanted)
        build_wanted "$variant" "$target" "$example_flag"
        ;;
    base)
        if [[ "$variant" != "job" ]]; then
            echo "Error: 'base' format is only available for 'job' variant." >&2
            exit 1
        fi
        build_base
        ;;
    all)
        build_full "$variant" "" "$target" "$example_flag"
        build_short "$variant" "$target" "$example_flag"
        build_wanted "$variant" "$target" "$example_flag"
        if [[ "$variant" == "job" && -z "$example_flag" ]]; then
            generate_notes "$target" "$clean_flag"
        fi
        ;;
    *)
        usage
        ;;
esac

#!/bin/bash
# Compile LaTeX paper into PDF
# Usage: compile_pdf.sh <input.tex> <output_dir>

set -euo pipefail

INPUT="$1"
OUTDIR="${2:-.}"

if [ ! -f "$INPUT" ]; then
    echo "Error: Input file '$INPUT' not found"
    exit 1
fi

BASENAME=$(basename "$INPUT" .tex)

# Detect compiler
if command -v xelatex >/dev/null 2>&1; then
    COMPILER=xelatex
elif command -v pdflatex >/dev/null 2>&1; then
    COMPILER=pdflatex
else
    echo "Error: No LaTeX compiler found (xelatex or pdflatex)"
    echo "Please install MiKTeX or TeX Live"
    exit 1
fi

echo "Compiling with: $COMPILER"

cd "$OUTDIR"

# Compile twice for TOC and cross-references
$COMPILER -interaction=nonstopmode -halt-on-error "${BASENAME}.tex" > /dev/null 2>&1 || {
    echo "First compilation failed"
    exit 1
}

# Run bibtex if .aux exists with bibliography
if [ -f "${BASENAME}.aux" ]; then
    if grep -q "bibdata" "${BASENAME}.aux" || grep -q "citation" "${BASENAME}.aux"; then
        bibtex "${BASENAME}.aux" > /dev/null 2>&1 || true
    fi
fi

# Second compilation
$COMPILER -interaction=nonstopmode -halt-on-error "${BASENAME}.tex" > /dev/null 2>&1 || {
    echo "Second compilation failed"
    exit 1
}

# Third compilation for TOC
$COMPILER -interaction=nonstopmode -halt-on-error "${BASENAME}.tex" > /dev/null 2>&1 || {
    echo "Third compilation failed"
    exit 1
}

if [ -f "${BASENAME}.pdf" ]; then
    echo "Success: ${OUTDIR}/${BASENAME}.pdf"
else
    echo "Error: PDF not generated"
    exit 1
fi

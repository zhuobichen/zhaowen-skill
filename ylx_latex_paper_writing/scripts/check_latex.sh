#!/bin/bash
# Check if LaTeX compiler is available
# Returns: 0 if available, 1 if not

if command -v xelatex >/dev/null 2>&1; then
    echo "xelatex found: $(which xelatex)"
    exit 0
elif command -v pdflatex >/dev/null 2>&1; then
    echo "pdflatex found: $(which pdflatex)"
    exit 0
elif command -v latex >/dev/null 2>&1; then
    echo "latex found: $(which latex)"
    exit 0
else
    echo "No LaTeX compiler found. Please install MiKTeX or TeX Live."
    exit 1
fi

---
name: ylx_latex_paper_writing
description: >
  Write academic papers in LaTeX and compile to PDF. Use when user asks to 
  "write a paper", "generate LaTeX", "compile PDF", "create paper template",
  or "write in LaTeX format". Handles environmental science papers on PM2.5/CMAQ
  data fusion, includes ICLR/arxiv style templates, bibtex management, and
  MiKTeX/xelatex compilation. Key files: templates/iclr_style.tex,
  scripts/compile_pdf.sh, scripts/check_latex.sh.
version: 1.0.0
---

# LaTeX Paper Writing Skill

Generate academic papers in LaTeX format and compile to PDF.

## Quick Start

```bash
# Check if LaTeX is available
./scripts/check_latex.sh

# Compile LaTeX to PDF
./scripts/compile_pdf.sh paper.tex output_dir/

# Or use xelatex directly
xelatex paper.tex
```

## Core Workflow

### 1. Select Template

| Template | Use Case | File |
|----------|----------|------|
| ICLR Style | Machine learning, general | `templates/iclr_style.tex` |
| Environmental Science | PM2.5, CMAQ, air quality | `templates/environmental_science.tex` |
| Blank Minimal | Custom format | `templates/minimal.tex` |

### 2. Write Paper Content

Follow standard academic structure:
```
1. Title & Abstract
2. Introduction
3. Related Work  
4. Methodology
5. Experiments
6. Results
7. Discussion
8. Conclusion
9. References
```

### 3. Compile to PDF

```bash
cd output_dir
xelatex paper.tex
bibtex paper.aux  # If using references
xelatex paper.tex
xelatex paper.tex  # Run twice for TOC
```

---

## Templates

### ICLR Style Template

Located at `templates/iclr_style.tex`:
- Standard academic layout
- AMS math environments
- Algorithm listings
- References via `\citep{}` and `\citet{}`

**Usage:**
```latex
\documentclass{article}
\usepackage{iclr2024_conference,times}
\input{templates/iclr_style.tex}
```

### Environmental Science Template

Located at `templates/environmental_science.tex`:
- Optimized for PM2.5, CMAQ, air quality research
- Custom commands for chemical formulas
- Tables for statistical metrics (R², MAE, RMSE)
- Figure reference patterns

**Usage:**
```latex
\documentclass{article}
\usepackage{environmental}
\input{templates/environmental_science.tex}
```

---

## Common LaTeX Commands

### Math

```latex
% Inline math
$y = f(x)$

% Display math
\begin{equation}
    P_{fused} = w_1 \cdot P_{obs} + w_2 \cdot P_{model}
\end{equation}

% Multi-line equation
\begin{align}
    R^2 &= 1 - \frac{\sum(y_{pred} - y_{true})^2}{\sum(y_{true} - \bar{y})^2} \\
    MAE &= \frac{1}{n}\sum|y_{pred} - y_{true}|
\end{align}
```

### Tables

```latex
\begin{table}[h]
\centering
\caption{Performance Comparison}
\label{tab:results}
\begin{tabular}{lccc}
\toprule
Method & R² & MAE & RMSE \\
\midrule
CMAQ & -0.04 & 20.47 & 29.25 \\
VNA & 0.80 & 7.75 & 12.86 \\
eVNA & 0.81 & 7.99 & 12.52 \\
\bottomrule
\end{tabular}
\end{table}
```

### Figures

```latex
\begin{figure}[t]
    \centering
    \includegraphics[width=0.8\textwidth]{figure.png}
    \caption{Schematic diagram of the proposed method}
    \label{fig:method}
\end{figure}

Figure \ref{fig:method} shows...
```

### References

```latex
% In preamble
\bibliographystyle{plain}
\bibliography{references}

% In text
\citep{author2020}      % (Author, 2020)
\citet{author2020}      % Author (2020)
```

---

## BibTeX Format

```bibtex
@article{author2020,
  title={Paper Title},
  author={Author, A. and Author, B.},
  journal={Journal Name},
  volume={1},
  number={1},
  pages={1--10},
  year={2020}
}

@inproceedings{author2021,
  title={Conference Paper},
  author={Author, A.},
  booktitle={Proceedings of Conference},
  year={2021}
}
```

---

## Scripts

### check_latex.sh

Check if LaTeX compiler is available.

```bash
./scripts/check_latex.sh
# Returns: 0 if available, 1 if not
```

### compile_pdf.sh

Compile LaTeX to PDF.

```bash
./scripts/compile_pdf.sh input.tex output_dir/

# Output: output_dir/input.pdf
```

**Requirements:**
- MiKTeX or TeX Live installed
- `xelatex` or `pdflatex` in PATH

---

## Tips

1. **Run xelatex twice** for TOC and cross-references
2. **Run bibtex** after first xelatex if using references
3. **Use \\citep{}** for parenthetical citations
4. **Use \\citet{}** for narrative citations
5. **Place figures early** to avoid float issues

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| "xelatex not found" | Install MiKTeX or TeX Live |
| "Font not found" | Use `pdflatex` instead of `xelatex` |
| "Reference undefined" | Run xelatex twice |
| "BibTeX not run" | Run bibtex between xelatex calls |


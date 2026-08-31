# Academic Paper Structure Guide

## Standard Sections

### 1. Title
- Concise, informative title
- Include method name if novel
- Subtitle if needed

### 2. Abstract (150-300 words)
- Problem statement (1-2 sentences)
- Approach (1-2 sentences)
- Key contributions (1-2 sentences)
- Results (1-2 sentences)
- Implications (optional)

### 3. Introduction
- Context and motivation
- Problem definition
- Gap in current research
- Proposed approach
- Main contributions (bullet list)
- Paper structure overview

### 4. Related Work
- Survey relevant prior work
- Organize by approach type
- Compare and contrast
- Position your work

### 5. Background/Problem Formulation
- Mathematical notation
- Problem definition
- Data description
- Evaluation metrics

### 6. Methodology
- Proposed method details
- Mathematical formulation
- Algorithm description
- Implementation details

### 7. Experiments
- Experimental setup
- Datasets
- Baselines
- Evaluation metrics
- Results (quantitative + qualitative)

### 8. Results
- Main results with tables/figures
- Statistical significance
- Ablation studies
- Error analysis

### 9. Discussion
- Interpretation of results
- Limitations
- Comparison with prior work
- Practical implications

### 10. Conclusion
- Summary of contributions
- Future work directions

### 11. References
- Consistent citation style
- Prioritize recent work
- Include key foundational papers

### 12. Appendix (optional)
- Proofs
- Additional experiments
- Implementation details

---

## For PM2.5/CMAQ Data Fusion Papers

### Specialized Sections

#### Data Description
- Study area (Beijing, North China)
- Monitoring network (number of stations, types)
- CMAQ model configuration
- Time period covered

#### Evaluation Metrics (required)
```
R² (coefficient of determination)
MAE (mean absolute error)
RMSE (root mean square error)
MB (mean bias)
```

#### Statistical Metrics Table Format
```latex
\begin{table}[h]
\centering
\caption{Performance comparison of methods}
\label{tab:results}
\begin{tabular}{lcccc}
\toprule
Method & \textbf{R²} $\uparrow$ & \textbf{MAE} $\downarrow$ & \textbf{RMSE} $\downarrow$ & \textbf{MB} \\
\midrule
CMAQ & -0.04 & 20.47 & 29.25 & -3.24 \\
VNA & 0.80 & 7.75 & 12.86 & +0.76 \\
eVNA & 0.81 & 7.99 & 12.52 & +0.08 \\
Proposed & \textbf{0.86} & \textbf{6.95} & \textbf{10.85} & \textbf{-0.00} \\
\bottomrule
\end{tabular}
\end{table}
```

#### Method Naming Conventions
| Method | Full Name | Context |
|--------|-----------|---------|
| VNA | Voronoi Neighbor Averaging | Baseline |
| eVNA | Extended VNA (multiplicative bias correction) | Baseline |
| aVNA | Additive VNA | Baseline |
| RK | Residual Kriging | Improved baseline |
| ST-CRK | Spatiotemporal Cooperative RK | Proposed |

#### Chemical Formulas
```
PM2.5: PM$_{2.5}$ or \PM
Ozone: O$_3$ or \ozone
NO2: NO$_2$ or \nitrogen
SO4: SO$_4^{2-}$ or \sulfate
```

---

## LaTeX Writing Tips

### Equations
```latex
% Inline
$y = f(x)$

% Display
\begin{equation}
    P_{fused} = w_1 \cdot P_{obs} + w_2 \cdot P_{model}
    \label{eq:fusion}
\end{equation}

% Multi-line align
\begin{align}
    R^2 &= 1 - \frac{\sum(y_{pred} - y_{true})^2}{\sum(y_{true} - \bar{y})^2} \label{eq:r2} \\
    MAE &= \frac{1}{n}\sum|y_{pred} - y_{true}| \label{eq:mae}
\end{align}
```

### Citations
```latex
% Parenthetical
\citep{author2020}

% Narrative
\citet{author2020} proposed...

% Multiple
\citep{author1, author2, author3}
```

### Figures
```latex
\begin{figure}[t]
    \centering
    \includegraphics[width=0.8\textwidth]{figure.png}
    \caption{Schematic diagram of the proposed method}
    \label{fig:method}
\end{figure}
```

### Tables
```latex
\begin{table}[h]
\centering
\caption{Method comparison}
\label{tab:methods}
\begin{tabular}{lcc}
\toprule
Method & R² & RMSE \\
\midrule
Baseline & 0.80 & 12.86 \\
Proposed & \textbf{0.86} & \textbf{10.85} \\
\bottomrule
\end{tabular}
\end{table}
```

---

## Common Mistakes to Avoid

1. **Title too vague**: Include key method/data info
2. **Abstract too long**: Keep under 300 words
3. **Missing baseline comparison**: Always compare to existing methods
4. **Inconsistent notation**: Define all symbols
5. **Missing uncertainty**: Include confidence intervals or error bars
6. **Overclaiming**: Be conservative in conclusions
7. **Poor figure quality**: Use vector graphics (PDF, PNG)
8. **Citation gaps**: Include foundational and recent work

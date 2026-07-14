# Mathematical and Engineering Reference

Formal definitions underlying `resonator_gen`. Minimal prose; symbols are defined once at first use and reused throughout.

## 1. Notation

| Symbol | Meaning | Units |
|---|---|---|
| $f$ | drive frequency | Hz |
| $c$ | vacuum speed of light | m/s |
| $\varepsilon_{\mathrm{eff}}$ | effective relative permittivity of the CPW mode | — |
| $v_\phi$ | phase velocity | m/s |
| $L$ | target electrical length | µm |
| $w, g$ | CPW center-conductor width, gap | µm |
| $r$ | bend radius | µm |
| $s$ | straight-segment length | µm |
| $\theta$ | arc subtended angle | rad |

## 2. Frequency–length calibration

$$
v_\phi = \frac{c}{\sqrt{\varepsilon_{\mathrm{eff}}}}, \qquad
v_\phi \leftarrow v_\phi^{\text{(kinetic override)}} \text{ if supplied}
$$

$$
L_{\lambda/4}(f) = \frac{v_\phi}{4f}, \qquad
L_{\lambda/2}(f) = \frac{v_\phi}{2f}
$$

Body length after coupler electrical correction $\delta L_c$ (config `coupler_dL_um`):

$$
L_{\text{body}}(f) = L_{\lambda/4}(f) - \delta L_c
$$

Inversion (round-trip check):

$$
f\big(L\big) = \frac{v_\phi}{4L}
$$

Implementation: `Calibration.target_length_um`, `Calibration.body_length_um`, `Calibration.frequency_hz_from_length` in [`calibration.py`](../src/resonator_gen/calibration.py).

## 3. Centerline length invariant

A centerline is an ordered sequence of straight segments $\{s_i\}$ and circular arcs $\{(r_j, \theta_j)\}$:

$$
L_{\text{path}} = \sum_i s_i \;+\; \sum_j r_j \left|\theta_j\right|
$$

This sum is computed directly from segment parameters — never from a GDS polygon boundary integral. For an arc parametrized by center $\mathbf{c}$, radius $r$, and angle sweep $\theta \in [\theta_0, \theta_1]$:

$$
\mathbf{p}(\theta) = \mathbf{c} + r\begin{pmatrix}\cos\theta \\ \sin\theta\end{pmatrix}, \qquad
\left\lVert \frac{d\mathbf{p}}{d\theta} \right\rVert = r
\;\Rightarrow\;
\int_{\theta_0}^{\theta_1} \left\lVert \frac{d\mathbf{p}}{d\theta}\right\rVert d\theta = r\,(\theta_1-\theta_0)
$$

confirming the closed form used. Numeric cross-check (`Centerline.numeric_length_um`) discretizes at $N \geq \max(2, \lceil s \cdot \rho \rceil + 1)$ samples per segment (sampling density $\rho$, default $100\,\mu\text{m}^{-1}$) and sums chord lengths; test tolerance $10^{-9}$ relative.

## 4. Meander width-solving (KQCircuits `Meander`, mirrored)

Given straight-line span $\ell$ between meander endpoints, bend radius $r$, and meander count $N$, the **bend length increment** for a single bend of transverse width $w$:

$$
\Delta\ell_{\text{bend}}(w) =
\begin{cases}
r\left(\dfrac{\pi}{2}-2\right) + w, & w \ge r \\[2mm]
r\left(2\arctan(1-x) + \dfrac{x + h(h-1)}{\sqrt{x^2+h^2}} - 1\right), & w < r
\end{cases}
\qquad h = \frac{w}{r},\quad x = \frac{1-h}{1-\frac{h}{2}}
$$

Total meander length increment over $N$ folds (end bends at $w/4$, interior bends at $w/2$):

$$
\Delta\ell_{\text{meander}}(w, N) = 4\,\Delta\ell_{\text{bend}}\!\left(\frac{w}{4}\right) + 2(N-1)\,\Delta\ell_{\text{bend}}\!\left(\frac{w}{2}\right)
$$

Target increment given body length $L_{\text{body}}$:

$$
\Delta\ell_{\text{target}} = L_{\text{body}} - \ell
$$

Width solve (piecewise; linear regime for all-90° bends, root-find otherwise):

$$
w^\star =
\begin{cases}
4r + \dfrac{\Delta\ell_{\text{target}} - \Delta\ell_{\text{meander}}(4r, N)}{N}, & \Delta\ell_{\text{target}} \ge \Delta\ell_{\text{meander}}(4r, N) \\[3mm]
\operatorname*{brentq}_{w \in [0,\, 4r]} \Big[\Delta\ell_{\text{meander}}(w, N) - \Delta\ell_{\text{target}}\Big] = 0, & \text{otherwise}
\end{cases}
$$

Automatic fold count (KQCircuits default when unspecified):

$$
N_{\text{auto}}(\ell, r) = \left\lfloor \frac{\ell}{2r} \right\rfloor - 1, \qquad \ell \ge 4r \text{ required}
$$

Implementation: `meander_width_required_um`, `meander_length_increment_um`, `bend_length_increment_um`, `auto_meander_count` in [`routing.py`](../src/resonator_gen/routing.py); validated against installed `kqcircuits.elements.meander.Meander` geometry (`bbox` height, $n=1$ single-sided fold, $n \ge 2$ symmetric folds) in `tests/test_anchored_placement.py::test_meander_width_parity_with_kqc`.

Required transverse corridor width (metal + protection margin $m$, default $5\,\mu\text{m}$):

$$
w_{\text{req}}(\ell) = w^\star(\ell) + \underbrace{(w_{\text{cpw}} + 2g)}_{\text{CPW footprint}} + 2m
$$

## 5. Design-rule constraints

With footprint $F = w_{\text{cpw}} + 2g$ and ratio floor $\kappa$ (default $3$):

$$
r \ge \kappa F \qquad \text{(bend radius)}, \qquad p \ge \kappa F \qquad \text{(meander pitch)}
$$

Soft mode: violation logged as warning. Hard mode: `ConstraintError` raised. Never silently accepted.

## 6. Keepout region algebra

All operations are exact Boolean set operations on polygon regions in integer database units $u = 10^{-3}\,\mu\text{m}$ (no rasterization, no distance transform).

Keepout union with source set $\mathcal{K} = \{K_1, \dots, K_n\}$:

$$
K_{\text{union}} = \bigcup_{i=1}^n K_i
$$

Isotropic growth by clearance $\delta$ (Minkowski sum with a disk of radius $\delta$, approximated by KLayout's polygon `size()` operator):

$$
K_{\text{grown}}(\delta) = K_{\text{union}} \oplus B_\delta, \qquad B_\delta = \{\mathbf{x} : \lVert \mathbf{x}\rVert \le \delta\}
$$

Keep-in region given die interior $D$ (die rectangle shrunk by edge margin $m_e$):

$$
\Omega(\delta) = D \setminus K_{\text{grown}}(\delta)
$$

Exactness property verified by test (not assumed): for all $\mathbf{x} \in \partial\Omega(\delta)$ nearest a keepout,

$$
\operatorname{dist}(\mathbf{x}, K_{\text{union}}) = \delta \quad \text{(within one database unit)}
$$

checked via KLayout's `Region.separation_check(K_{\text{union}}, \delta/u)`: zero violating pairs at $\delta$, nonzero at $\delta + 2u$.

## 7. Anchored corridor placement search

**Local frame.** Given fixed anchor $\mathbf{P}$ and direction $\phi$ (no direction search — $\phi$ is fixed by the coupler tap), transform:

$$
\Omega_{\text{local}} = R(-\phi)\,\big(\Omega(\delta) - \mathbf{P}\big)
$$

so the corridor axis is the local $+x$ axis starting at the origin.

**Containment test.** For candidate span $\ell$ (measured from the lead offset $\ell_0$) and corridor half-width $\frac{h}{2}$, define the axis-aligned rectangle

$$
\mathcal{R}(\ell, h) = \left[\ell_0,\, \ell_0+\ell+\tfrac{F}{2}\right] \times \left[-\tfrac{h}{2}, \tfrac{h}{2}\right]
$$

Containment is exact set difference emptiness:

$$
\mathcal{R}(\ell, h) \subseteq \Omega_{\text{local}} \iff \mathcal{R}(\ell,h) \setminus \Omega_{\text{local}} = \varnothing
$$

**Feasibility.** A span $\ell$ is feasible for a meander with fold count $N(\ell) = N_{\text{auto}}(\ell, r)$ iff

$$
\mathcal{R}\big(\ell,\, w_{\text{req}}(\ell)\big) \subseteq \Omega_{\text{local}}
$$

Since $w_{\text{req}}(\ell)$ is piecewise-decreasing (with jump discontinuities at each $N$ increment) and the maximum available width $w_{\text{avail}}(\ell)$ is non-increasing, feasibility is **not monotone** in $\ell$; a bisection on $\ell$ alone is invalid.

**Search.** Deterministic grid scan with step $\Delta\ell = \tfrac{1}{2}r$ over

$$
\ell \in \Big[4r,\; \ell_{\max}\Big], \qquad \ell_{\max} = \sup\{x : \mathcal{R}(x, 2u) \subseteq \Omega_{\text{local}}\}
$$

($\ell_{\max}$ itself found by bisection on a degenerate thin corridor, tolerance $u$). At each grid point, evaluate feasibility and area $A(\ell) = \ell \cdot w_{\text{req}}(\ell)$; retain

$$
\ell^\star = \operatorname*{arg\,min}_{\ell \text{ feasible}} A(\ell)
$$

then refine over $[\ell^\star - \Delta\ell,\ \ell^\star + \Delta\ell]$ with $17$ evenly spaced evaluation points (fixed count $\Rightarrow$ deterministic, no adaptive step).

**Spiral fallback.** If no meander span is feasible, maximize anchored rectangle area directly (independent of the meander width law) over the same grid:

$$
(\ell^\star, h^\star) = \operatorname*{arg\,max}_{\ell} \; \ell \cdot w_{\text{avail}}(\ell), \qquad
\text{subject to } \max\!\left(\frac{\ell}{w_{\text{avail}}(\ell)}, \frac{w_{\text{avail}}(\ell)}{\ell}\right) \le \gamma
$$

with aspect cap $\gamma = 2$. Estimated fill capacity at spiral pitch $p = 2r$:

$$
\hat{L}_{\text{spiral}} = \frac{\ell^\star \, h^\star}{p}
$$

used only as an admissibility filter; the real `SpiralResonatorPolygon` build (in a scratch layout) verifies $\left|L_{\text{actual}} - L_{\text{body}}\right| \le \epsilon_{\text{spiral}}$ ($\epsilon_{\text{spiral}} = 1\,\mu\text{m}$) before committing the placement.

**Failure.** If neither geometry yields a feasible rectangle, raise with diagnostics

$$
\text{shortfall} = \max\!\big(0,\; L_{\text{body}} - L_{\text{best-feasible}}\big)
$$

Implementation: `find_anchored_placement`, `_meander_candidate`, `_spiral_placement` in [`routing.py`](../src/resonator_gen/routing.py).

## 8. Sequential keepout accumulation

For resonators placed in config order $R_1, \dots, R_n$, keepout state evolves as

$$
K^{(0)} = K_{\text{feedline}} \cup \bigcup_{u \in \text{YAML keepouts}} u, \qquad
K^{(i)} = K^{(i-1)} \cup \Gamma\!\left(R_i\right)
$$

where $\Gamma(R_i)$ is the union of the gap layer and ground-grid-avoidance layer regions of the built cell for $R_i$. Resonator $R_{i}$ is placed against $\Omega^{(i-1)}(\delta_i) = D \setminus \left(K^{(i-1)} \oplus B_{\delta_i}\right)$, guaranteeing order-dependent but fully deterministic, non-overlapping results.

## 9. Verification tolerances (summary table)

| Check | Tolerance | Rationale |
|---|---|---|
| Analytic vs. numeric centerline length | $10^{-9}$ relative | pure arithmetic, no discretization in the analytic path |
| Manual-mode meander body length | $5\times10^{-3}\,\mu\text{m}$ | KLayout path annotation quantizes near $1\,\text{nm} = u$ |
| Auto-mode meander body length | $5\times10^{-2}\,\mu\text{m}$ | solved (non-round) spans increase corner count, compounding per-vertex $u$-grid rounding |
| Frequency round-trip | $10^{-4}$ relative | numerical precision only; excludes physical calibration uncertainty |
| Keep-in clearance | $\le 1$ dbu at $\delta$; violations must appear by $\delta + 2u$ | exactness of `Region.size()` |
| Spiral realized length | $1\,\mu\text{m}$ | `SpiralResonatorPolygon` fill is not closed-form; verified by build-and-measure |

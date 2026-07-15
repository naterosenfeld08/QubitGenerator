"""Shared helpers for running KQCircuits -> Elmer simulation batches."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from kqcircuits.simulations.export.elmer.elmer_export import export_elmer
from kqcircuits.simulations.export.elmer.elmer_solution import ElmerSolution


def default_workflow(*, gmsh_threads: int = 4, elmer_threads: int = 2) -> dict:
    return {
        "run_gmsh": True,
        "run_gmsh_gui": False,
        "run_elmergrid": True,
        "run_elmer": True,
        "run_paraview": False,
        "gmsh_n_threads": gmsh_threads,
        "elmer_n_processes": 1,
        "elmer_n_threads": elmer_threads,
        "python_executable": sys.executable,
    }


def run_batch(
    sims: list,
    out_dir: Path,
    *,
    prefix: str = "batch",
    workflow: dict | None = None,
    clean: bool = True,
) -> Path:
    """Export and execute an Elmer batch; return the output directory."""
    out_dir = Path(out_dir)
    if clean and out_dir.exists():
        import shutil

        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wf = workflow or default_workflow()
    script = export_elmer(sims, out_dir, file_prefix=prefix, workflow=wf)
    result = subprocess.run(
        ["bash", Path(script).name],
        cwd=str(Path(script).parent),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-40:])
        raise RuntimeError(f"Elmer batch failed in {out_dir}:\n{tail}")
    return out_dir


def load_results(out_dir: Path, sim_name: str) -> dict:
    """Load ``{sim_name}_project_results.json`` from an Elmer batch directory."""
    path = out_dir / f"{sim_name}_project_results.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())

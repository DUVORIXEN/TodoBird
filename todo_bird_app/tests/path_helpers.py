from pathlib import Path

def project_root() -> Path:
    """Returns the absolute path to the project root directory."""
    return Path(__file__).resolve().parent.parent.parent

def production_db_path() -> Path:
    """Returns the absolute path to the production database."""
    return project_root() / "todo_bird_app" / "data" / "todo_bird.db"

def benchmark_db_path() -> Path:
    """Returns the absolute path to the benchmark database."""
    return project_root() / "todo_bird_app" / "data" / "benchmark_test.db"

"""RSSCM Baseline Builder — Magic Import Pipeline CLI."""
import click


@click.group()
def main():
    """RSSCM Baseline Builder — normalize vendor deliveries into the RSSCM standard."""


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--store", type=click.Path(), help="Store binaries to this directory.")
def ingest(path, store):
    """Ingest a vendor delivery (zip/folder), extract and classify files."""
    from rsscm_import.ingest import ingest_delivery

    result = ingest_delivery(path, store_dir=store)
    for entry in result:
        click.echo(f"[{entry['type']:12s}] {entry['path']}  ({entry['size']} bytes, sha256={entry['sha256'][:16]}...)")
    click.echo(f"\n{len(result)} files classified.")


@main.command("parse-ladeliste")
@click.argument("path", type=click.Path(exists=True))
def parse_ladeliste(path):
    """Parse a vendor Ladeliste (Excel/CSV) into normalized software items."""
    from rsscm_import.ladeliste import parse_ladeliste as _parse
    import json

    items = _parse(path)
    click.echo(json.dumps(items, indent=2, default=str))
    click.echo(f"\n{len(items)} software items parsed.")


@main.command("current-state")
@click.argument("path", type=click.Path(exists=True))
def current_state(path):
    """Load current train state from CMDB export (Excel)."""
    from rsscm_import.cmdb import read_current_state
    import json

    state = read_current_state(path)
    click.echo(json.dumps(state, indent=2, default=str))
    click.echo(f"\n{len(state)} items in current state.")


@main.command()
@click.option("--delivery", type=click.Path(exists=True), required=True, help="Vendor Ladeliste file.")
@click.option("--current", type=click.Path(exists=True), required=True, help="CMDB export file.")
def diff(delivery, current):
    """Compute diff between vendor delivery and current train state."""
    from rsscm_import.ladeliste import parse_ladeliste
    from rsscm_import.cmdb import read_current_state
    from rsscm_import.diff import compute_diff

    delivery_items = parse_ladeliste(delivery)
    current_items = read_current_state(current)
    result = compute_diff(delivery_items, current_items)

    for status in ("NEW", "UPDATED", "UNCHANGED"):
        items = [i for i in result if i["status"] == status]
        if items:
            click.echo(f"\n{'='*40}\n{status} ({len(items)}):\n{'='*40}")
            for i in items:
                click.echo(f"  {i['name']} {i.get('version', '')}  [{i.get('component', '')}]")


@main.command()
@click.option("--delivery", type=click.Path(exists=True), required=True)
@click.option("--current", type=click.Path(exists=True), required=True)
@click.option("--api-url", default="http://localhost:8000/api/", help="Django backend URL.")
@click.option("--dry-run", is_flag=True, help="Print payloads without calling API.")
def push(delivery, current, api_url, dry_run):
    """Push normalized data to Django backend."""
    from rsscm_import.ladeliste import parse_ladeliste
    from rsscm_import.cmdb import read_current_state
    from rsscm_import.diff import compute_diff
    from rsscm_import.api_client import push_to_backend

    delivery_items = parse_ladeliste(delivery)
    current_items = read_current_state(current)
    result = compute_diff(delivery_items, current_items)
    clean = [i for i in result if i["status"] in ("NEW", "UPDATED")]
    push_to_backend(clean, api_url=api_url, dry_run=dry_run)


@main.command()
@click.option("--delivery", type=click.Path(exists=True), required=True, help="Vendor delivery zip.")
@click.option("--ladeliste", type=click.Path(exists=True), required=True, help="Vendor Ladeliste file.")
@click.option("--current-state", "current", type=click.Path(exists=True), required=True, help="CMDB export.")
@click.option("--api-url", default="http://localhost:8000/api/", help="Django backend URL.")
@click.option("--store", type=click.Path(), default="./assets", help="Asset storage directory.")
@click.option("--dry-run", is_flag=True, help="Print payloads without calling API.")
def run(delivery, ladeliste, current, api_url, store, dry_run):
    """Run the full import pipeline: ingest → parse → diff → push + store."""
    from rsscm_import.ingest import ingest_delivery
    from rsscm_import.ladeliste import parse_ladeliste
    from rsscm_import.cmdb import read_current_state
    from rsscm_import.diff import compute_diff
    from rsscm_import.api_client import push_to_backend
    from rsscm_import.storage import store_assets

    click.echo("=== Ingesting delivery ===")
    files = ingest_delivery(delivery, store_dir=store)
    click.echo(f"  {len(files)} files classified.")

    click.echo("\n=== Parsing Ladeliste ===")
    delivery_items = parse_ladeliste(ladeliste)
    click.echo(f"  {len(delivery_items)} software items parsed.")

    click.echo("\n=== Loading current state ===")
    current_items = read_current_state(current)
    click.echo(f"  {len(current_items)} items in current state.")

    click.echo("\n=== Computing diff ===")
    result = compute_diff(delivery_items, current_items)
    new = [i for i in result if i["status"] == "NEW"]
    updated = [i for i in result if i["status"] == "UPDATED"]
    unchanged = [i for i in result if i["status"] == "UNCHANGED"]
    click.echo(f"  {len(new)} new, {len(updated)} updated, {len(unchanged)} unchanged")

    click.echo("\n=== Storing assets ===")
    store_assets(files, store)

    click.echo("\n=== Pushing to backend ===")
    clean = new + updated
    push_to_backend(clean, api_url=api_url, dry_run=dry_run)

    click.echo(f"\n✓ Clean baseline ready: {len(clean)} items to install/update.")

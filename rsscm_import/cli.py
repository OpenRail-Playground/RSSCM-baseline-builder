"""RSSCM Baseline Builder — Magic Import Pipeline CLI."""
import json

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


@main.command("parse")
@click.argument("path", type=click.Path(exists=True))
@click.option("--level", help="Filter to a tree level (e.g. Software).")
def parse(path, level):
    """Parse a delivery (any supported format) into normalized items."""
    from rsscm_import.delivery import parse_delivery

    items = [i.to_dict() for i in parse_delivery(path)]
    if level:
        items = [i for i in items if i["level"] == level]
    click.echo(json.dumps(items, indent=2, default=str))
    click.echo(f"\n{len(items)} items parsed.")


@main.command("current-state")
@click.argument("path", type=click.Path(exists=True))
def current_state(path):
    """Load current train state from CMDB export."""
    from rsscm_import.cmdb import read_current_state

    state = read_current_state(path)
    click.echo(json.dumps(state, indent=2, default=str))
    click.echo(f"\n{len(state)} items in current state.")


@main.command()
@click.option("--delivery", type=click.Path(exists=True), required=True, help="Vendor delivery (zip/file).")
@click.option("--current", type=click.Path(exists=True), required=True, help="CMDB export.")
@click.option("--level", help="Only report changes at this tree level (e.g. Software).")
def diff(delivery, current, level):
    """Compute diff between vendor delivery and current train state."""
    from rsscm_import.delivery import parse_delivery
    from rsscm_import.cmdb import read_current_state
    from rsscm_import.diff import compute_diff, summarize

    delivery_items = [i.to_dict() for i in parse_delivery(delivery)]
    current_items = read_current_state(current)
    result = compute_diff(delivery_items, current_items)
    s = summarize(result)

    changes = s["changes"]
    if level:
        changes = [c for c in changes if c["level"] == level]
    click.echo(f"\n{s['new']} new, {s['updated']} updated, {s['unchanged']} unchanged")
    click.echo(f"{'='*60}\nDISTINCT CHANGES ({len(changes)}):\n{'='*60}")
    for c in changes:
        prev = c.get("previous_version", "—")
        click.echo(f"  [{c['status']:7s}] [{c['level']}] {c['subsystem']} / {c['system_component']} / "
                   f"{c['name']}:  {prev} -> {c['version']}")


@main.command()
@click.option("--delivery", type=click.Path(exists=True), required=True)
@click.option("--current", type=click.Path(exists=True), required=True)
@click.option("--api-url", default="http://localhost:8000/api/v1/", help="Django backend URL.")
@click.option("--level", default="Software", help="Push changes at this level (default: Software).")
@click.option("--dry-run", is_flag=True, help="Print payloads without calling API.")
def push(delivery, current, api_url, level, dry_run):
    """Push normalized changes to the Django backend."""
    from rsscm_import.delivery import parse_delivery
    from rsscm_import.cmdb import read_current_state
    from rsscm_import.diff import compute_diff, summarize
    from rsscm_import.api_client import push_to_backend

    delivery_items = [i.to_dict() for i in parse_delivery(delivery)]
    current_items = read_current_state(current)
    result = compute_diff(delivery_items, current_items)
    changes = summarize(result)["changes"]
    if level:
        changes = [c for c in changes if c["level"] == level]
    push_to_backend(changes, api_url=api_url, dry_run=dry_run)


@main.command()
@click.option("--delivery", type=click.Path(exists=True), required=True, help="Vendor delivery zip.")
@click.option("--current-state", "current", type=click.Path(exists=True), required=True, help="CMDB export.")
@click.option("--api-url", default="http://localhost:8000/api/v1/", help="Django backend URL.")
@click.option("--store", type=click.Path(), default="./assets", help="Asset storage directory.")
@click.option("--level", default="Software", help="Push changes at this level (default: Software).")
@click.option("--dry-run", is_flag=True, help="Print payloads without calling API.")
def run(delivery, current, api_url, store, level, dry_run):
    """Run the full import pipeline: parse → diff → push + store."""
    from rsscm_import.ingest import ingest_delivery
    from rsscm_import.delivery import parse_delivery
    from rsscm_import.cmdb import read_current_state
    from rsscm_import.diff import compute_diff, summarize
    from rsscm_import.api_client import push_to_backend
    from rsscm_import.storage import store_assets

    click.echo("=== Ingesting & classifying delivery files ===")
    files = ingest_delivery(delivery, store_dir=store)
    click.echo(f"  {len(files)} files classified.")

    click.echo("\n=== Parsing delivery into standard model ===")
    delivery_items = [i.to_dict() for i in parse_delivery(delivery)]
    click.echo(f"  {len(delivery_items)} normalized items.")

    click.echo("\n=== Loading current train state (CMDB) ===")
    current_items = read_current_state(current)
    click.echo(f"  {len(current_items)} items in current state.")

    click.echo("\n=== Computing diff (deduplicated) ===")
    result = compute_diff(delivery_items, current_items)
    s = summarize(result)
    click.echo(f"  {s['new']} new, {s['updated']} updated, {s['unchanged']} unchanged")

    click.echo("\n=== Storing assets ===")
    store_assets(files, store)

    click.echo("\n=== Pushing clean baseline to backend ===")
    changes = [c for c in s["changes"] if not level or c["level"] == level]
    push_to_backend(changes, api_url=api_url, dry_run=dry_run)

    click.echo(f"\n✓ Clean baseline ready: {len(changes)} item(s) to install/update.")


@main.command()
@click.option("--current-state", "current", type=click.Path(exists=True), required=True, help="Full current train state export.")
@click.option("--delivery", type=click.Path(exists=True), required=True, help="Provider delivery (zip/file).")
@click.option("--vehicle-type", default="Hacktrain", help="Train identity to attach the baseline to.")
@click.option("--api-url", default="http://localhost:8000/api/v1/", help="Django backend URL.")
@click.option("--dry-run", is_flag=True, help="Print payloads without calling API.")
def populate(current, delivery, vehicle_type, api_url, dry_run):
    """Populate the backend with the FULL current train baseline (as a vehicle
    type) and apply the delivery's updates — a realistic, queryable dataset."""
    from rsscm_import.delivery import parse_delivery
    from rsscm_import.cmdb import read_current_state
    from rsscm_import.diff import compute_diff, summarize
    from rsscm_import.api_client import populate_full_baseline

    click.echo("=== Loading full current train state ===")
    current_items = read_current_state(current)
    click.echo(f"  {len(current_items)} items.")

    click.echo("\n=== Parsing delivery & computing updates ===")
    delivery_items = [i.to_dict() for i in parse_delivery(delivery)]
    changes = summarize(compute_diff(delivery_items, current_items))["changes"]
    click.echo(f"  {len(changes)} change(s) from the delivery.")

    click.echo(f"\n=== Populating backend (vehicle type: {vehicle_type}) ===")
    stats = populate_full_baseline(current_items, changes, vehicle_type, api_url=api_url, dry_run=dry_run)
    click.echo(f"\n✓ Backend populated: {stats['seeded_items']} baseline items, "
               f"{stats['updates_applied']} pending update(s).")


@main.command()
@click.option("--api-url", default="http://localhost:8000/api/v1/", help="Django backend URL.")
@click.option("--vehicle-type", help="Show the baseline + pending updates for this train.")
@click.option("--component", help="Show the software running on this (sub)component.")
def query(api_url, vehicle_type, component):
    """Query the backend (for the demo): train baseline, pending updates, or a component."""
    from rsscm_import import query as q

    if vehicle_type:
        base = q.train_baseline(api_url, vehicle_type)
        if not base["found"]:
            click.echo(f"Vehicle type '{vehicle_type}' not found.")
            return
        click.echo(f"\n=== Baseline for {vehicle_type}: {base['count']} software items ===")
        for row in base["items"][:15]:
            click.echo(f"  {row['name']} ({row['software_type']}): {', '.join(row['versions']) or '—'}")
        if base["count"] > 15:
            click.echo(f"  … and {base['count'] - 15} more")

        pending = q.needs_update(api_url, vehicle_type)
        click.echo(f"\n=== {vehicle_type}: {len(pending)} item(s) NEED UPDATING ===")
        for p in pending:
            vs = p["versions"]
            click.echo(f"  ⚠ {p['name']} ({p['software_type']}): installed {vs[0]} → available {vs[-1]}")

    if component:
        comp = q.component_software(api_url, component)
        if not comp["found"]:
            click.echo(f"\nComponent '{component}' not found.")
            return
        click.echo(f"\n=== Software on '{component}': {comp['count']} item(s) ===")
        for row in comp["items"]:
            click.echo(f"  {row['name']} ({row['software_type']}): {', '.join(row['versions']) or '—'}")

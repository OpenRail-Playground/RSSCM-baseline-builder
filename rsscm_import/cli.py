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
@click.option("--delivery", type=click.Path(exists=True), default=None, help="Provider delivery (zip/file) — only needed with --apply-updates.")
@click.option("--fixture", type=click.Path(), default=None, help="Write a Django loaddata fixture to this path instead of pushing (faithful match incl. component_revision).")
@click.option("--apply-updates", is_flag=True, help="Also append the delivery's introduced versions as extra releases (off = pure current-baseline match).")
@click.option("--api-url", default="http://localhost:8000/api/v1/", help="Django backend URL.")
@click.option("--dry-run", is_flag=True, help="Print payloads without calling API.")
def populate(current, delivery, fixture, apply_updates, api_url, dry_run):
    """Build the train baseline model (Train → Subsystem → System → Software,
    with Hardware/Bare Metal components — matching the RSSCM example/v2.json) from
    the current train state, then either push it to the backend or write a Django
    loaddata fixture (--fixture). Use --apply-updates to also fold in a delivery."""
    from rsscm_import.cmdb import read_current_state
    from rsscm_import import baseline_v2 as baseline

    click.echo("=== Loading full current train state ===")
    current_items = read_current_state(current)
    click.echo(f"  {len(current_items)} items.")

    click.echo("\n=== Building baseline model (Train → Subsystem → System → Software) ===")
    model = baseline.build_model(current_items)
    click.echo(f"  {len(model.items)} items, {len(model.components)} hardware components.")

    if apply_updates:
        if not delivery:
            raise click.UsageError("--apply-updates requires --delivery")
        from rsscm_import.delivery import parse_delivery
        from rsscm_import.diff import compute_diff, summarize
        delivery_items = [i.to_dict() for i in parse_delivery(delivery)]
        changes = summarize(compute_diff(delivery_items, current_items))["changes"]
        applied = baseline.apply_updates(model, changes)
        click.echo(f"  applied {applied} delivery update release(s).")

    if fixture:
        import json
        data = baseline.to_fixture(model)
        with open(fixture, "w") as fh:
            json.dump(data, fh, indent=2)
        click.echo(f"\n✓ Wrote loaddata fixture ({len(data)} objects) to {fixture}")
        click.echo(f"  Load it with:  python manage.py loaddata {fixture}")
        return

    click.echo(f"\n=== Pushing baseline to {api_url} ===")
    stats = baseline.push_via_api(model, api_url=api_url, dry_run=dry_run)
    click.echo(f"\n✓ Pushed {stats['items']} items, {stats['components']} components, "
               f"{stats['releases']} releases (note: component_revision not settable via API).")


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

"""`assara status [CODE...]`: notes done and pending per source. This is the reference count."""

from __future__ import annotations

from ..library import index_status, list_sources, source_dir, sync_index


def configure(sub) -> None:
    p = sub.add_parser("status", help="notes done and remaining per source")
    p.add_argument("codes", nargs="*", help="only these sources")
    p.add_argument("--pending", action="store_true", help="show only sources with pending notes")
    p.add_argument(
        "--sync", action="store_true", help="write (done) in INDEX.md for every unit whose note exists"
    )
    p.set_defaults(func=run)


def run(args, cfg) -> int:
    dirs = [source_dir(cfg, c, create=False) for c in args.codes] if args.codes else list_sources(cfg)
    if not dirs:
        print("No source yet. Add one with `assara add CODE FILE`.")
        return 0
    total_done = total = 0
    print(f"{'Code':<12} {'Notes':>7}  Remaining")
    for d in dirs:
        if args.sync:
            for unit in sync_index(d):
                print(f"{d.name}: {unit} marked done in INDEX.md")
        done, count, pending = index_status(d)
        total_done += done
        total += count
        if args.pending and not pending:
            continue
        rest = ", ".join(pending) if pending else ("complete" if count else "no INDEX.md")
        print(f"{d.name:<12} {done:>3}/{count:<3}  {rest}")
    print(f"{'TOTAL':<12} {total_done:>3}/{total:<3}")
    return 0

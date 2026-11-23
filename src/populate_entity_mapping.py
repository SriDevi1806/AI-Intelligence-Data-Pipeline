from database import get_session, Startup, EntityMappingLog
from entity_resolver import resolve_entity, save_entity_mapping


def main():
    print("=" * 60)
    print("POPULATING STARTUP ENTITY MAPPING LOG")
    print("=" * 60)

    # Read plain values while the session is open.
    with get_session() as session:
        startups = session.query(
            Startup.id,
            Startup.name,
            Startup.source_url
        ).all()

        existing = {
            (
                m.original_name,
                m.canonical_name,
                m.entity_type,
                m.source_url
            )
            for m in session.query(EntityMappingLog).all()
        }

    print(f"Startup records scanned: {len(startups)}")

    saved = 0
    skipped = 0
    unresolved = 0
    failed = 0

    for startup_id, original_name, source_url in startups:

        if not original_name:
            unresolved += 1
            continue

        result = resolve_entity(original_name)

        if not result.get("resolved"):
            unresolved += 1
            continue

        canonical_name = result["canonical_name"]

        key = (
            original_name,
            canonical_name,
            "startup",
            source_url
        )

        if key in existing:
            skipped += 1
            continue

        try:
            success = save_entity_mapping(
                result,
                entity_type="startup",
                source_url=source_url
            )

            if success:
                saved += 1
                existing.add(key)

                with get_session() as session:
                    record = session.query(Startup).filter(
                        Startup.id == startup_id
                    ).first()

                    if record:
                        record.normalized_name = canonical_name
            else:
                failed += 1

        except Exception as exc:
            failed += 1
            print(f"ERROR: {original_name}: {exc}")

    print("\n" + "=" * 60)
    print("ENTITY MAPPING SUMMARY")
    print("=" * 60)
    print(f"Scanned:       {len(startups)}")
    print(f"New mappings:  {saved}")
    print(f"Already saved: {skipped}")
    print(f"Unresolved:    {unresolved}")
    print(f"Failed:        {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()

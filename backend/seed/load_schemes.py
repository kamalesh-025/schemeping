"""Idempotent seed loader.

Run with::

    python -m seed.load_schemes            # load everything
    python -m seed.load_schemes --dry-run  # validate and report, write nothing

Behaviour:
- Upserts by stable natural keys (``schemes.slug``, ``facilities.external_ref``).
- Never overwrites ``status`` on an existing scheme, so a scheme an admin has
  published is not pushed back to draft by re-running the seed.
- Refuses to load files with malformed eligibility rules.
- Never publishes anything by default: seed files are drafts pending human
  verification. ``--publish-sample-schemes`` MAY be used in non-production
  environments only, to make the sample schemes visible in the app.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.db import SessionLocal, engine
from app.models import Base, Facility, Scheme
from app.models.enums import SchemeStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from seed.schema import (
    SAMPLE_DATA_WARNING,
    FacilitySeed,
    SchemeSeed,
    SeedValidationError,
    load_facility_file,
    load_scheme_files,
)


@dataclass
class SeedReport:
    schemes_created: int = 0
    schemes_updated: int = 0
    facilities_created: int = 0
    facilities_updated: int = 0
    published: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"schemes: {self.schemes_created} created, {self.schemes_updated} updated",
            f"facilities: {self.facilities_created} created, "
            f"{self.facilities_updated} updated",
        ]
        if self.published:
            lines.append(f"published sample schemes: {self.published}")
        lines.extend(f"warning: {warning}" for warning in self.warnings)
        return "\n".join(lines)


def _scheme_values(scheme: SchemeSeed) -> dict[str, object]:
    return {
        "name": scheme.name,
        "department": scheme.department,
        "level": scheme.level,
        "state": scheme.state,
        "category": scheme.category,
        "scope": scheme.scope,
        "benefit_summary": scheme.benefit_summary,
        "benefit_amount": scheme.benefit_amount,
        "benefit_type": scheme.benefit_type,
        "eligibility_rules": scheme.eligibility_rules,
        "required_documents": [doc.model_dump() for doc in scheme.required_documents],
        "application_steps": [step.model_dump() for step in scheme.application_steps],
        "apply_url": str(scheme.apply_url) if scheme.apply_url else None,
        "deadline": scheme.deadline,
        "priority": scheme.priority,
        "last_verified_on": scheme.last_verified_on,
        "source_url": str(scheme.source_url),
    }


def upsert_scheme(session: Session, scheme: SchemeSeed) -> bool:
    """Insert or update one scheme. Returns True when a row was created."""
    existing = session.scalar(select(Scheme).where(Scheme.slug == scheme.slug))
    values = _scheme_values(scheme)

    if existing is None:
        session.add(Scheme(slug=scheme.slug, status=SchemeStatus.DRAFT, **values))
        return True

    for key, value in values.items():
        setattr(existing, key, value)
    return False


def upsert_facility(session: Session, facility: FacilitySeed) -> bool:
    existing = session.scalar(
        select(Facility).where(Facility.external_ref == facility.external_ref)
    )
    values: dict[str, object] = {
        "name": facility.name,
        "type": facility.type,
        "address": facility.address,
        "district": facility.district,
        "state": facility.state,
        "pincode": facility.pincode,
        "phone": facility.phone,
        "working_hours": facility.working_hours,
        "location": (facility.longitude, facility.latitude),
        "verified_on": facility.verified_on,
        "source_url": str(facility.source_url),
    }

    if existing is None:
        session.add(Facility(external_ref=facility.external_ref, **values))
        return True

    for key, value in values.items():
        setattr(existing, key, value)
    return False


def seed_all(session: Session) -> SeedReport:
    report = SeedReport()
    schemes = load_scheme_files()
    facilities = load_facility_file()

    for scheme in schemes:
        if upsert_scheme(session, scheme):
            report.schemes_created += 1
        else:
            report.schemes_updated += 1
        if scheme.status != SchemeStatus.DRAFT:
            report.warnings.append(
                f"{scheme.slug}: seed file requested status={scheme.status}; "
                "seed data is always loaded as draft"
            )

    for facility in facilities:
        if upsert_facility(session, facility):
            report.facilities_created += 1
        else:
            report.facilities_updated += 1

    session.commit()
    return report


def ensure_tables() -> None:
    """Create tables if the migration has not been run yet (handy for fresh clones)."""
    Base.metadata.create_all(bind=engine)


def publish_sample_schemes(session: Session) -> int:
    """Set every seeded sample scheme to ``published`` (DEV ONLY).

    Shows up in ``GET /eligibility`` on a development database. Refused when
    ``APP_ENV`` is ``production``: sample data must never go live unreviewed.
    Returns the number of schemes updated.
    """
    from app.core.config import get_settings

    settings = get_settings()
    if settings.app_env == "production":
        raise SeedValidationError(
            "Refusing to publish sample schemes in production. "
            "Real schemes must be admin-reviewed first."
        )

    count = 0
    schemes = session.scalars(select(Scheme)).all()
    for scheme in schemes:
        if scheme.status != SchemeStatus.PUBLISHED:
            scheme.status = SchemeStatus.PUBLISHED
            count += 1
    session.commit()
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load verified scheme seed data")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and parse seed files without touching the database",
    )
    parser.add_argument(
        "--publish-sample-schemes",
        action="store_true",
        help=(
            "DEV ONLY outside production: also set every sample scheme to "
            "published so they show up in the app"
        ),
    )
    args = parser.parse_args(argv)
    if args.dry_run and args.publish_sample_schemes:
        parser.error("--publish-sample-schemes cannot be combined with --dry-run")

    if args.dry_run:
        try:
            schemes = load_scheme_files()
            facilities = load_facility_file()
        except SeedValidationError as exc:
            print(f"Seed validation failed: {exc}", file=sys.stderr)
            return 1
        print(f"Validated {len(schemes)} schemes and {len(facilities)} facilities.")
        print(f"NOTE: {SAMPLE_DATA_WARNING}")
        return 0

    try:
        load_scheme_files()
        load_facility_file()
    except SeedValidationError as exc:
        print(f"Seed validation failed: {exc}", file=sys.stderr)
        return 1

    ensure_tables()
    started = datetime.now(tz=UTC)
    with SessionLocal() as session:
        report = seed_all(session)
        if args.publish_sample_schemes:
            report.published = publish_sample_schemes(session)

    print(report.summary())
    print(f"Completed in {(datetime.now(tz=UTC) - started).total_seconds():.2f}s")
    print(f"NOTE: {SAMPLE_DATA_WARNING}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

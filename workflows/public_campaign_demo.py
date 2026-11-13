"""Run the real campaign app against public pages in a disposable local database."""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from workflows import demo


def seed_brands(service, cases):
    from api.brand_translate import domain_key_from_url
    from api.user_auth import hash_password

    user = service.create_user(email=f"review-{uuid4().hex[:12]}@adzy.invalid",
                               hashed_password=hash_password("LocalCampaignReview42"))
    brands = {}
    with service._uow_factory() as uow:
        for case in cases:
            item = json.loads((case / "brand.json").read_text())
            domain = domain_key_from_url(item["url"])
            if domain in brands.values():
                raise ValueError("Duplicate brand")
            brand = uow.brands.lock_or_create_for_scrape(
                domain_key=domain, user_id=user.id, display_name=item["name"], source_url=item["url"],
            ).brand
            profile = uow.profiles.create_version_for_locked_brand(
                brand_id=brand.id,
                profile={"source_url": item["url"], "name": {"value": item["name"], "source_type": "owner_input"}},
                schema_version=1,
            )
            uow.brands.set_current_profile(brand_id=brand.id, profile_id=profile.id)
            brands[case.name] = domain
        uow.commit()
    return {"actor": str(user.id), "email": user.email, "brands": brands, "synthetic": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "serve", "cleanup"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--case", type=Path, action="append", default=[])
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    demo.isolate(offline=args.action != "serve")
    directory = args.directory.resolve()
    if args.action == "init":
        demo.init(directory, seed_demo=lambda service, _: seed_brands(service, args.case))
        manifest = json.loads((directory / "demo.json").read_text())
        print(json.dumps({"email": manifest["email"], "password": "LocalCampaignReview42"}))
        return
    manifest = json.loads((directory / "demo.json").read_text())
    if args.action == "cleanup":
        name = manifest["container"]
        if not name.startswith("adzy-review-demo-") or demo.command([
            "docker", "inspect", "--format", '{{ index .Config.Labels "adzy.review-demo" }}', name,
        ]) != "true":
            raise ValueError("Not an ADZY demo resource")
        demo.command(["docker", "stop", name])
        return
    from db.test_database_safety import require_disposable_test_database

    require_disposable_test_database(manifest["dsn"], environ={
        "BASEERA_DESTRUCTIVE_TEST_DATABASE": "baseera_pytest_foundation",
    })
    if manifest["synthetic"] or "brands" not in manifest:
        raise ValueError("Expected a public campaign demo database")
    os.environ.update(PERSISTENCE_BACKEND="postgres", BASEERA_DATABASE_URL=manifest["dsn"],
                      BASEERA_WEBAPP_DIR=str(directory / "application"), ADZY_REVIEW_STATE_DIR=str(directory / "review"))
    import uvicorn
    from api.main import app

    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

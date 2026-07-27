import argparse
import getpass
import os

from sqlalchemy import select

from app.database.models import User
from app.database.session import SessionLocal
from app.services import platform_auth


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the first MoneyPrinterTurbo platform administrator."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    password = os.getenv("MPT_BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Administrator password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            parser.error("passwords do not match")

    with SessionLocal.begin() as db:
        if db.scalar(select(User.id).where(User.system_role == "admin")):
            parser.error("an administrator already exists")
        try:
            user = platform_auth.create_user_with_workspace(
                db,
                email=args.email,
                password=password,
                display_name=args.name,
                system_role="admin",
            )
            platform_auth.audit(
                db, "bootstrap.admin_created", "user", user.id, user.id
            )
        except ValueError as exc:
            parser.error(str(exc))

    print(f"Administrator created: {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

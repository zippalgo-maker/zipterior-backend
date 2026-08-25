import argparse
import sys
from getpass import getpass
from pathlib import Path

from sqlalchemy import text


BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.database import SessionLocal
from app.core.security import hash_password


def create_super_admin() -> None:
    email = input("최고관리자 이메일: ").strip().lower()
    name = input("최고관리자 이름: ").strip()
    password = getpass("최고관리자 비밀번호: ")
    password_confirm = getpass("비밀번호 확인: ")

    if not email or not name:
        raise SystemExit("이메일과 이름은 필수입니다.")

    if len(password) < 8:
        raise SystemExit("비밀번호는 최소 8자 이상이어야 합니다.")

    if password != password_confirm:
        raise SystemExit("비밀번호가 일치하지 않습니다.")

    with SessionLocal() as session:
        existing = session.execute(
            text(
                """
                SELECT id, role, status
                FROM users
                WHERE email = :email
                  AND deleted_at IS NULL
                """
            ),
            {"email": email},
        ).mappings().one_or_none()

        if existing:
            raise SystemExit(
                f"이미 등록된 이메일입니다. "
                f"id={existing['id']} "
                f"role={existing['role']} "
                f"status={existing['status']}"
            )

        user_id = session.execute(
            text(
                """
                INSERT INTO users (
                    email,
                    password_hash,
                    name,
                    role,
                    status,
                    email_verified_at,
                    marketing_agreed
                )
                VALUES (
                    :email,
                    :password_hash,
                    :name,
                    'super_admin',
                    'active',
                    NOW(),
                    FALSE
                )
                RETURNING id
                """
            ),
            {
                "email": email,
                "password_hash": hash_password(password),
                "name": name,
            },
        ).scalar_one()

        session.commit()

    print("최고관리자 생성 완료")
    print("USER_ID:", user_id)
    print("EMAIL:", email)


def list_admins() -> None:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT id, email, name, role, status, created_at
                FROM users
                WHERE role IN ('admin', 'super_admin')
                  AND deleted_at IS NULL
                ORDER BY id
                """
            )
        ).mappings().all()

    if not rows:
        print("관리자 계정이 없습니다.")
        return

    for row in rows:
        print(
            f"id={row['id']} "
            f"email={row['email']} "
            f"name={row['name']} "
            f"role={row['role']} "
            f"status={row['status']}"
        )


def list_pending_companies() -> None:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT
                    c.id,
                    c.name,
                    c.business_number,
                    c.status,
                    u.email AS owner_email,
                    c.created_at
                FROM companies AS c
                JOIN users AS u
                  ON u.id = c.owner_user_id
                WHERE c.status = 'pending'
                ORDER BY c.created_at
                """
            )
        ).mappings().all()

    if not rows:
        print("승인 대기 업체가 없습니다.")
        return

    for row in rows:
        print(
            f"id={row['id']} "
            f"name={row['name']} "
            f"business_number={row['business_number']} "
            f"owner_email={row['owner_email']} "
            f"status={row['status']}"
        )


def show_status() -> None:
    with SessionLocal() as session:
        db = session.execute(
            text(
                """
                SELECT
                    current_user,
                    current_database(),
                    current_setting('timezone')
                """
            )
        ).one()

        counts = session.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS users,
                    (SELECT COUNT(*) FROM companies) AS companies,
                    (
                        SELECT COUNT(*)
                        FROM companies
                        WHERE status = 'pending'
                    ) AS pending_companies,
                    (
                        SELECT COUNT(*)
                        FROM event_outbox
                        WHERE status = 'pending'
                    ) AS pending_events
                """
            )
        ).mappings().one()

    print("Database user:", db[0])
    print("Database:", db[1])
    print("Timezone:", db[2])
    print("Users:", counts["users"])
    print("Companies:", counts["companies"])
    print("Pending companies:", counts["pending_companies"])
    print("Pending events:", counts["pending_events"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Zipterior 관리 명령"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    commands.add_parser(
        "create-super-admin",
        help="최고관리자 생성",
    )
    commands.add_parser(
        "list-admins",
        help="관리자 목록",
    )
    commands.add_parser(
        "list-pending-companies",
        help="승인 대기 업체 목록",
    )
    commands.add_parser(
        "status",
        help="서버 DB 상태 요약",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "create-super-admin":
        create_super_admin()
    elif args.command == "list-admins":
        list_admins()
    elif args.command == "list-pending-companies":
        list_pending_companies()
    elif args.command == "status":
        show_status()


if __name__ == "__main__":
    main()

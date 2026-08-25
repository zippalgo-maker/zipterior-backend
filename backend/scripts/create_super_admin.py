from getpass import getpass

from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.security import hash_password


def main() -> None:
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
                SELECT id
                FROM users
                WHERE email = :email
                  AND deleted_at IS NULL
                """
            ),
            {"email": email},
        ).scalar_one_or_none()

        if existing is not None:
            raise SystemExit("이미 등록된 이메일입니다.")

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


if __name__ == "__main__":
    main()

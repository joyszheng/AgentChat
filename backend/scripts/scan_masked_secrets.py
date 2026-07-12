"""扫描 system_settings 中被"掩码"污染或无法解密的加密配置。

历史上，前端回显的脱敏掩码（如 ``abc******xyz``）可能被误当成新密钥重新加密
存入库里，导致该密钥其实是一串带 ``*`` 的掩码。本脚本解密每个加密配置并检测：

- 解密后仍像掩码（含 ``***`` 或全为 ``******``）→ 被污染，需要重新填写。
- 解密直接失败（如 ENCRYPTION_KEY 变过）→ 无法使用，需要重新填写。

默认只读报告，不打印任何明文。加 ``--fix`` 会删除异常行（应用随后回退到
.env/默认值），之后到设置页重新填写真实值即可。

用法（在 backend 目录）::

    uv run python scripts/scan_masked_secrets.py
    uv run python scripts/scan_masked_secrets.py --fix
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services.encryption import decrypt_value  # noqa: E402


def _looks_like_mask(value: str) -> bool:
    stripped = (value or "").strip()
    return not stripped or stripped == "******" or "***" in stripped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="扫描被掩码污染或无法解密的加密配置。"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="删除异常行（之后到设置页重新填写真实值）。默认只读。",
    )
    args = parser.parse_args()

    problems: list[tuple[str, str]] = []
    with SessionLocal() as db:
        rows = (
            db.query(models.SystemSetting)
            .filter(models.SystemSetting.is_encrypted.is_(True))
            .order_by(models.SystemSetting.key.asc())
            .all()
        )
        print(f"扫描 {len(rows)} 个加密配置...\n")

        for row in rows:
            try:
                decrypted = decrypt_value(row.value)
            except Exception as exc:  # noqa: BLE001 - 汇总所有解密失败
                status = f"解密失败({type(exc).__name__})"
            else:
                status = "掩码污染" if _looks_like_mask(decrypted) else "正常"

            flag = "" if status == "正常" else "  <-- 需重新填写"
            print(f"  {row.key:24} {status}{flag}")
            if status != "正常":
                problems.append((row.key, status))

        if not problems:
            print("\n未发现异常，所有加密配置均可正常解密且非掩码。")
            return 0

        print(f"\n共发现 {len(problems)} 个异常项。")
        if args.fix:
            for key, _status in problems:
                setting = db.query(models.SystemSetting).filter(
                    models.SystemSetting.key == key
                ).first()
                if setting is not None:
                    db.delete(setting)
            db.commit()
            print("已删除异常项，应用将回退到 .env/默认值。请到设置页重新填写真实值。")
        else:
            print("只读模式：确认无误后加 --fix 删除这些异常项，再到设置页重新填写。")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

from sqlalchemy.orm import Session

from .. import models


def get_system_setting(db: Session, key: str):
    """按 key 查询系统配置。"""
    return db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()


def list_system_settings(db: Session, category: str | None = None):
    """查询系统配置列表，可按分类筛选。"""
    query = db.query(models.SystemSetting)

    if category is not None:
        query = query.filter(models.SystemSetting.category == category)

    return query.order_by(models.SystemSetting.category, models.SystemSetting.key).all()


def upsert_system_setting(
    db: Session,
    *,
    key: str,
    value: str,
    category: str,
    is_encrypted: bool = False,
    description: str | None = None,
):
    """创建或更新系统配置。"""
    setting = get_system_setting(db, key)

    if setting is None:
        setting = models.SystemSetting(
            key=key,
            value=value,
            category=category,
            is_encrypted=is_encrypted,
            description=description,
        )
        db.add(setting)
    else:
        setting.value = value
        setting.category = category
        setting.is_encrypted = is_encrypted
        if description is not None:
            setting.description = description

    db.commit()
    db.refresh(setting)
    return setting


def delete_system_setting(db: Session, key: str) -> bool:
    """删除系统配置；配置不存在时返回 False。"""
    setting = get_system_setting(db, key)

    if setting is None:
        return False

    db.delete(setting)
    db.commit()
    return True

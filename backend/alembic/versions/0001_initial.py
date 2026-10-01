"""Create the initial AI Producer schema and sample dataset."""

from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


TITLES = [
    "Build a landing page in 20 min",
    "3 prompts for better UI",
    "Stop making this layout mistake",
    "My AI coding workflow",
    "Fix spacing with one rule",
    "A homepage that converts",
    "Design faster with constraints",
    "The CTA test I use",
    "Why your hero feels empty",
    "Turn a brief into a layout",
    "Mobile nav without clutter",
    "Make every section scannable",
    "Audit any layout in 5 minutes",
    "Build dense screens that breathe",
    "One prompt for sharper copy",
    "A better designer handoff",
    "Plan before you code",
    "When cards hurt hierarchy",
    "Responsive checklist before launch",
    "Ship a simple site today",
]

HOOKS = [
    "Соберите первый экран за 20 минут и оставьте одно главное действие.",
    "Три запроса помогают быстро найти слабые места интерфейса.",
    "Эта ошибка ломает иерархию даже в аккуратном макете.",
    "Вот как я превращаю идею в рабочий интерфейс вместе с AI.",
    "Один принцип отступов делает страницу заметно спокойнее.",
    "Конверсия начинается с ясного обещания на первом экране.",
    "Ограничения ускоряют дизайн сильнее, чем бесконечный выбор.",
    "Этот тест показывает, понимает ли пользователь вашу кнопку.",
    "Пустой hero часто скрывает отсутствие конкретного оффера.",
    "Разложите brief на смысловые блоки до начала верстки.",
    "Мобильная навигация должна помогать, а не занимать экран.",
    "Сканируемая секция отвечает на один вопрос за раз.",
    "За пять минут можно найти главные ошибки любого layout.",
    "Плотный экран остаётся понятным, если правильно расставить акценты.",
    "Один prompt помогает убрать воду и усилить главное сообщение.",
    "Хороший handoff объясняет решение, а не только показывает макет.",
    "Сначала план страницы, потом компоненты и визуальные детали.",
    "Карточки нужны только там, где они показывают иерархию.",
    "Проверьте эти пункты до того, как открыть макет на телефоне.",
    "Простой сайт можно выпустить сегодня, если убрать лишнее.",
]

TOPICS = [
    ["лендинг", "первый экран", "скорость"],
    ["AI", "prompt", "интерфейс"],
    ["layout", "иерархия", "ошибки"],
    ["AI coding", "workflow", "разработка"],
    ["отступы", "design system", "ритм"],
    ["конверсия", "homepage", "оффер"],
    ["ограничения", "процесс", "скорость"],
    ["CTA", "тестирование", "конверсия"],
    ["hero", "оффер", "композиция"],
    ["brief", "layout", "структура"],
    ["mobile", "навигация", "UX"],
    ["секции", "сканирование", "контент"],
    ["аудит", "layout", "UX"],
    ["плотность", "таблица", "читабельность"],
    ["copy", "prompt", "редактура"],
    ["handoff", "команда", "дизайн"],
    ["планирование", "лендинг", "структура"],
    ["карточки", "иерархия", "UI"],
    ["responsive", "mobile", "чек-лист"],
    ["запуск", "MVP", "сайт"],
]


def upgrade() -> None:
    op.create_table(
        "competitors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("handle", sa.String(length=128), nullable=False, unique=True),
        sa.Column("profile_url", sa.String(length=512), nullable=False, unique=True),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("avatar_url", sa.String(length=1024)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_import_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitors_handle", "competitors", ["handle"], unique=True)
    op.create_index("ix_competitors_is_active", "competitors", ["is_active"])

    op.create_table(
        "reels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("competitor_id", sa.Integer(), sa.ForeignKey("competitors.id"), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("original_url", sa.String(length=1024)),
        sa.Column("thumbnail_url", sa.String(length=1024)),
        sa.Column("media_path", sa.String(length=1024)),
        sa.Column("thumb_variant", sa.Integer(), nullable=False),
        sa.Column("is_saved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reels_competitor_id", "reels", ["competitor_id"])
    op.create_index("ix_reels_external_id", "reels", ["external_id"], unique=True)
    op.create_index("ix_reels_title", "reels", ["title"])
    op.create_index("ix_reels_author", "reels", ["author"])
    op.create_index("ix_reels_is_saved", "reels", ["is_saved"])

    op.create_table(
        "remixes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=255), nullable=False, unique=True),
        sa.Column("source_reel_id", sa.Integer(), sa.ForeignKey("reels.id")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("cta", sa.Text(), nullable=False),
        sa.Column("thread_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_remixes_slug", "remixes", ["slug"], unique=True)
    op.create_index("ix_remixes_source_reel_id", "remixes", ["source_reel_id"])
    op.create_index("ix_remixes_status", "remixes", ["status"])

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("competitor_id", sa.Integer(), sa.ForeignKey("competitors.id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_import_jobs_competitor_id", "import_jobs", ["competitor_id"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])

    op.create_table(
        "app_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_events_event_type", "app_events", ["event_type"])
    op.create_index("ix_app_events_entity_type", "app_events", ["entity_type"])
    op.create_index("ix_app_events_entity_id", "app_events", ["entity_id"])

    now = datetime.now(timezone.utc)
    competitor_table = sa.table(
        "competitors",
        sa.column("id", sa.Integer),
        sa.column("handle", sa.String),
        sa.column("profile_url", sa.String),
        sa.column("category", sa.String),
        sa.column("language", sa.String),
        sa.column("avatar_url", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("last_import_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        competitor_table,
        [{
            "id": 1,
            "handle": "@buildwithalex",
            "profile_url": "https://instagram.com/buildwithalex",
            "category": "Веб-разработка",
            "language": "EN",
            "avatar_url": None,
            "is_active": True,
            "last_import_at": now,
            "created_at": now,
            "updated_at": now,
        }],
    )

    views = [128000, 87000, 64000, 112000, 73000, 96000, 51000, 84000, 69000, 105000, 58000, 76000, 91000, 67000, 119000, 54000, 88000, 62000, 98000, 71000]
    durations = [42, 36, 28, 51, 33, 47, 31, 39, 44, 52, 29, 41, 38, 35, 49, 32, 45, 37, 53, 40]
    reel_table = sa.table(
        "reels",
        sa.column("id", sa.Integer),
        sa.column("competitor_id", sa.Integer),
        sa.column("external_id", sa.String),
        sa.column("title", sa.String),
        sa.column("hook", sa.Text),
        sa.column("topics", sa.JSON),
        sa.column("search_text", sa.Text),
        sa.column("author", sa.String),
        sa.column("views", sa.Integer),
        sa.column("duration_seconds", sa.Integer),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("original_url", sa.String),
        sa.column("thumbnail_url", sa.String),
        sa.column("media_path", sa.String),
        sa.column("thumb_variant", sa.Integer),
        sa.column("is_saved", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        reel_table,
        [
            {
                "id": index + 1,
                "competitor_id": 1,
                "external_id": f"seed-reel-{index + 1}",
                "title": title,
                "hook": HOOKS[index],
                "topics": TOPICS[index],
                "search_text": " ".join([title, HOOKS[index], "@buildwithalex", *TOPICS[index]]).lower(),
                "author": "@buildwithalex",
                "views": views[index],
                "duration_seconds": durations[index],
                "published_at": now - timedelta(days=index),
                "original_url": f"https://instagram.com/reel/seed-{index + 1}",
                "thumbnail_url": None,
                "media_path": None,
                "thumb_variant": (index % 4) + 1,
                "is_saved": False,
                "created_at": now,
                "updated_at": now,
            }
            for index, title in enumerate(TITLES)
        ],
    )

    remix_table = sa.table(
        "remixes",
        *[sa.column(name) for name in [
            "id", "slug", "source_reel_id", "title", "brief", "hook", "script", "cta", "thread_text",
            "status", "created_at", "updated_at",
        ]],
    )
    op.bulk_insert(
        remix_table,
        [{
            "id": 1,
            "slug": "landing-20-minutes",
            "source_reel_id": 1,
            "title": "Лендинг за 20 минут",
            "brief": "",
            "hook": "Твой лендинг теряет заявки в первые 5 секунд.",
            "script": "Покажи первый экран до и после. Убери лишний текст, оставь один оффер и заметную кнопку. Проверь мобильную версию.",
            "cta": "Сохрани чек-лист и проверь свой сайт.",
            "thread_text": "Хороший лендинг начинается с ясного оффера. Один экран, одна мысль, одно действие.",
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }],
    )

    import_table = sa.table(
        "import_jobs",
        *[sa.column(name) for name in [
            "id", "competitor_id", "provider", "status", "requested_count", "imported_count", "error_message",
            "started_at", "completed_at", "created_at", "updated_at",
        ]],
    )
    op.bulk_insert(
        import_table,
        [{
            "id": 1,
            "competitor_id": 1,
            "provider": "seed",
            "status": "completed",
            "requested_count": 20,
            "imported_count": 20,
            "error_message": None,
            "started_at": now,
            "completed_at": now,
            "created_at": now,
            "updated_at": now,
        }],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table_name in ("competitors", "reels", "remixes", "import_jobs"):
            op.execute(
                sa.text(
                    f"select setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"coalesce((select max(id) from {table_name}), 1), true)"
                )
            )


def downgrade() -> None:
    op.drop_table("app_events")
    op.drop_table("import_jobs")
    op.drop_table("remixes")
    op.drop_table("reels")
    op.drop_table("competitors")

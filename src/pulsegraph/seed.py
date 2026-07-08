"""Seed the local database with a rich demo dataset.

Usage:
    uv run python src/pulsegraph/seed.py

Creates a realistic, deliberately messy dataset so every dashboard surface
has something to show — including the failure paths:

* several users (one admin), each with watches in every state
  (active, user-paused, and auto-deactivated after repeated failures);
* a month of pipeline runs with a high failure rate and varied errors,
  plus a couple of drift-paused and stuck-running runs;
* full provenance chains item -> analysis -> evaluation -> notification
  with a mix of Ollama/Claude models and confidence levels;
* the things that went wrong: failed and dead-lettered notifications,
  pending retries, a drifting/paused source, a populated review queue,
  and cost events pushing one user toward the budget cap;
* notification-channel settings, review decisions, and audit entries.

Idempotent: no-ops if the demo user already exists.
"""

import datetime
import hashlib
import random
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pulsegraph.api.auth import hash_password
from pulsegraph.config import get_settings
from pulsegraph.db import models as m
from pulsegraph.domain import enums
from pulsegraph.domain.constants import EMBEDDING_DIM
from pulsegraph.pipeline.prompts import ensure_default_prompts

# Deterministic output so re-seeding a fresh database is reproducible.
random.seed(1337)

_UTC = datetime.UTC

# --- content pools --------------------------------------------------------

_RUN_ERRORS = [
    "Source timeout: JobTech API did not respond within 30s",
    "Schema validation failed: unexpected field 'headline' missing",
    "Rate limit hit: 429 from upstream, backing off",
    "Ollama connection refused on http://localhost:11434",
    "Embedding dimension mismatch: got 512, expected 768",
    "Claude API error: overloaded_error (529)",
    "Parse error: malformed JSON in raw_payload",
    "Cost cap exceeded for this billing period",
    "Redis unavailable: rate-limit check failed open",
    "Deserialization error in graph checkpoint",
]

_DRIFT_DETAILS = {
    enums.SourceKind.JOBTECH: (
        "Schema drift: 'workplace_address' object changed shape; "
        "sampled fetch no longer validates"
    ),
    enums.SourceKind.RIKSDAGEN: (
        "Feed returned HTTP 500 on 4 consecutive probes"
    ),
    enums.SourceKind.ENTSOE: ("Auth token rejected: security token expired"),
}

_SUMMARIES = {
    enums.SourceKind.JOBTECH: [
        "New senior backend role at a Stockholm fintech; Python + AWS, "
        "hybrid remote, matches the watch closely.",
        "Data engineering position mentioning dbt and Snowflake; partial "
        "match on the machine-learning angle.",
        "Junior support role misfiled under engineering; low relevance to "
        "the query.",
    ],
    enums.SourceKind.RIKSDAGEN: [
        "Committee motion referencing the EU AI Act transparency articles; "
        "directly on topic for the watch.",
        "Interpellation on grid capacity and wind expansion in SE3; "
        "relevant to the energy-policy watch.",
        "Procedural notice with no substantive policy content; not relevant.",
    ],
    enums.SourceKind.ENTSOE: [
        "Day-ahead wind generation forecast for SE3 revised up 12%; "
        "notable capacity signal.",
        "Cross-border flow schedule update SE3->DK1; minor relevance.",
        "Routine outage notice for a small unit; below the interest "
        "threshold.",
    ],
}

_CLAUDE_VERSIONS = ["claude-opus-4-8", "claude-sonnet-5"]
_OLLAMA_VERSIONS = ["llama3.2", "qwen2.5:7b"]

# --- user + watch specifications ------------------------------------------

_USERS = [
    {
        "email": "demo@pulsegraph.dev",
        "pw": "demo1234",
        "role": enums.UserRole.USER,
        "consent": True,
    },
    {
        "email": "admin@pulsegraph.dev",
        "pw": "admin1234",
        "role": enums.UserRole.ADMIN,
        "consent": True,
    },
    {
        "email": "alice@pulsegraph.dev",
        "pw": "alice1234",
        "role": enums.UserRole.USER,
        "consent": True,
    },
    {
        "email": "bob@pulsegraph.dev",
        "pw": "bob1234",
        "role": enums.UserRole.USER,
        "consent": False,
    },
    {
        "email": "carol@pulsegraph.dev",
        "pw": "carol1234",
        "role": enums.UserRole.USER,
        "consent": True,
    },
]

# (source, prompt, hours, state) where state is "active" | "paused" |
# "deactivated" (auto-deactivated after repeated failures, ADR 0015).
_WATCH_SPECS = {
    "demo@pulsegraph.dev": [
        (
            enums.SourceKind.JOBTECH,
            "Python developer remote Stockholm",
            1,
            "active",
        ),
        (
            enums.SourceKind.JOBTECH,
            "Senior data engineer machine learning",
            2,
            "active",
        ),
        (enums.SourceKind.JOBTECH, "Backend engineer Rust or Go", 3, "paused"),
        (
            enums.SourceKind.JOBTECH,
            "Platform SRE Kubernetes",
            6,
            "deactivated",
        ),
        (
            enums.SourceKind.RIKSDAGEN,
            "EU AI Act regulations parliament motions",
            6,
            "active",
        ),
        (
            enums.SourceKind.RIKSDAGEN,
            "Climate and energy policy 2025",
            12,
            "paused",
        ),
        (
            enums.SourceKind.ENTSOE,
            "Wind power capacity SE3 bidding zone",
            4,
            "active",
        ),
        (
            enums.SourceKind.ENTSOE,
            "Cross-border flows SE3 to DK1",
            8,
            "active",
        ),
    ],
    "alice@pulsegraph.dev": [
        (
            enums.SourceKind.JOBTECH,
            "Frontend React TypeScript remote",
            2,
            "active",
        ),
        (
            enums.SourceKind.JOBTECH,
            "Engineering manager fintech",
            12,
            "active",
        ),
        (
            enums.SourceKind.RIKSDAGEN,
            "Healthcare digitalization reform",
            24,
            "paused",
        ),
        (
            enums.SourceKind.ENTSOE,
            "Solar generation forecast SE4",
            6,
            "deactivated",
        ),
    ],
    "bob@pulsegraph.dev": [
        (enums.SourceKind.JOBTECH, "DevOps Terraform GCP", 3, "active"),
        (
            enums.SourceKind.RIKSDAGEN,
            "Defense procurement debate",
            12,
            "active",
        ),
        (enums.SourceKind.ENTSOE, "Nuclear availability SE3", 8, "active"),
    ],
    "carol@pulsegraph.dev": [
        (enums.SourceKind.JOBTECH, "Staff ML engineer LLM", 1, "active"),
        (
            enums.SourceKind.RIKSDAGEN,
            "AI liability directive transposition",
            4,
            "active",
        ),
    ],
    "admin@pulsegraph.dev": [
        (
            enums.SourceKind.ENTSOE,
            "System operator balancing SE1",
            6,
            "active",
        ),
    ],
}

# Users whose Claude spend is deliberately high (drives the admin costs
# view toward the cap).
_HEAVY_SPENDERS = {"carol@pulsegraph.dev", "demo@pulsegraph.dev"}


def _vector() -> list[float]:
    return [round(random.random(), 6) for _ in range(EMBEDDING_DIM)]


def _hash(*parts: object) -> str:
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode()).hexdigest()


def _ts(now: datetime.datetime, days_ago: float) -> datetime.datetime:
    t = now - datetime.timedelta(days=days_ago)
    return t.replace(
        hour=random.randint(6, 22),
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
        microsecond=0,
    )


def seed() -> None:  # noqa: C901 - a linear, readable data builder
    settings = get_settings()
    engine = create_engine(settings.database_url)
    now = datetime.datetime.now(_UTC)

    with Session(engine) as session:
        ensure_default_prompts(session)

        exists = session.execute(
            text("SELECT 1 FROM users WHERE email = 'demo@pulsegraph.dev'")
        ).first()
        if exists:
            print("Already seeded — skipping.")
            return

        analyzer_prompt = (
            session.query(m.Prompt)
            .filter(
                m.Prompt.role == enums.PromptRole.ANALYZER,
                m.Prompt.is_active.is_(True),
            )
            .first()
        )
        prompt_id = analyzer_prompt.id if analyzer_prompt else None

        # A second (inactive) analyzer version so the prompt history has
        # something to show in the admin Prompts tab.
        if analyzer_prompt:
            session.add(
                m.Prompt(
                    id=uuid.uuid4(),
                    name=analyzer_prompt.name,
                    role=enums.PromptRole.ANALYZER,
                    version=analyzer_prompt.version + 1,
                    template=analyzer_prompt.template
                    + "\n\nBe concise and cite the source.",
                    is_active=False,
                )
            )

        # --- users ---
        users: dict[str, m.User] = {}
        for spec in _USERS:
            u = m.User(
                id=uuid.uuid4(),
                email=spec["email"],
                password_hash=hash_password(spec["pw"]),
                role=spec["role"],
                consented_at=now if spec["consent"] else None,
            )
            users[spec["email"]] = u
        session.add_all(list(users.values()))
        session.flush()
        admin_id = users["admin@pulsegraph.dev"].id

        # --- source health: one source is drifting/paused ---
        session.add_all(
            [
                m.SourceHealth(
                    source=enums.SourceKind.JOBTECH,
                    status=enums.SourceStatus.PAUSED,
                    drift_detail=_DRIFT_DETAILS[enums.SourceKind.JOBTECH],
                    last_checked_at=now - datetime.timedelta(hours=2),
                ),
                m.SourceHealth(
                    source=enums.SourceKind.RIKSDAGEN,
                    status=enums.SourceStatus.HEALTHY,
                    last_checked_at=now - datetime.timedelta(minutes=20),
                ),
                m.SourceHealth(
                    source=enums.SourceKind.ENTSOE,
                    status=enums.SourceStatus.HEALTHY,
                    last_checked_at=now - datetime.timedelta(minutes=8),
                ),
            ]
        )

        # --- notification settings (email + webhook for some users) ---
        settings_rows = [
            m.NotificationSetting(
                user_id=users["demo@pulsegraph.dev"].id,
                channel=enums.NotificationChannel.EMAIL,
                frequency=enums.NotificationFrequency.INSTANT,
                destination="demo@pulsegraph.dev",
                is_active=True,
            ),
            m.NotificationSetting(
                user_id=users["demo@pulsegraph.dev"].id,
                channel=enums.NotificationChannel.WEBHOOK,
                frequency=enums.NotificationFrequency.DAILY_DIGEST,
                destination="https://example.com/hooks/pulsegraph",
                is_active=True,
            ),
            m.NotificationSetting(
                user_id=users["alice@pulsegraph.dev"].id,
                channel=enums.NotificationChannel.EMAIL,
                frequency=enums.NotificationFrequency.DAILY_DIGEST,
                destination="alice@pulsegraph.dev",
                is_active=True,
            ),
            m.NotificationSetting(
                user_id=users["carol@pulsegraph.dev"].id,
                channel=enums.NotificationChannel.WEBHOOK,
                frequency=enums.NotificationFrequency.INSTANT,
                destination="https://example.com/hooks/carol",
                is_active=True,
            ),
        ]
        session.add_all(settings_rows)

        # --- watches, runs, and provenance chains ---
        watches: list[m.Watch] = []
        for email, specs in _WATCH_SPECS.items():
            user = users[email]
            for source, prompt, hours, state in specs:
                is_active = state == "active"
                w = m.Watch(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    source=source,
                    prompt=prompt,
                    is_active=is_active,
                    schedule_interval=datetime.timedelta(hours=hours),
                    last_run_at=_ts(now, 0),
                    next_run_at=now + datetime.timedelta(hours=hours),
                    config={},
                )
                w._email = email  # transient tag for the run loop
                w._state = state
                watches.append(w)
        session.add_all(watches)
        session.flush()

        runs: list[m.PipelineRun] = []
        items: list[m.Item] = []
        analyses: list[m.Analysis] = []
        evaluations: list[m.Evaluation] = []
        notifications: list[m.Notification] = []
        cost_events: list[m.CostEvent] = []
        review_targets: list[m.Evaluation] = []

        for w in watches:
            user = users[w._email]
            heavy = w._email in _HEAVY_SPENDERS
            n_runs = random.randint(10, 26)
            # A deactivated watch failed repeatedly before being switched off.
            fail_weight = 0.6 if w._state == "deactivated" else 0.28

            gave_running = False
            for _ in range(n_runs):
                days_ago = random.uniform(0, 29)
                roll = random.random()
                if roll < fail_weight:
                    status = enums.RunStatus.FAILED
                elif roll < fail_weight + 0.08:
                    status = enums.RunStatus.PAUSED
                elif (
                    not gave_running
                    and w._state == "active"
                    and random.random() < 0.05
                ):
                    status = enums.RunStatus.RUNNING
                    gave_running = True
                else:
                    status = enums.RunStatus.SUCCEEDED

                started = _ts(now, days_ago)
                if status == enums.RunStatus.RUNNING:
                    finished = None
                    error = None
                elif status == enums.RunStatus.FAILED:
                    finished = started + datetime.timedelta(
                        seconds=random.randint(3, 40)
                    )
                    error = random.choice(_RUN_ERRORS)
                elif status == enums.RunStatus.PAUSED:
                    finished = started + datetime.timedelta(
                        seconds=random.randint(2, 15)
                    )
                    error = (
                        "Source paused by drift detection; run halted "
                        "before fetch"
                    )
                else:
                    finished = started + datetime.timedelta(
                        seconds=random.randint(6, 95)
                    )
                    error = None

                run = m.PipelineRun(
                    id=uuid.uuid4(),
                    watch_id=w.id,
                    status=status,
                    started_at=started,
                    finished_at=finished,
                    error=error,
                    langsmith_trace_id=(
                        uuid.uuid4().hex
                        if status == enums.RunStatus.SUCCEEDED
                        and random.random() < 0.4
                        else None
                    ),
                )
                runs.append(run)

                if status != enums.RunStatus.SUCCEEDED:
                    continue

                # Provenance chain for a couple of items on a good run.
                for _ in range(random.randint(0, 3)):
                    summary = random.choice(_SUMMARIES[w.source])
                    long_hit = summary.startswith(("New", "Committee", "Day"))
                    seq = len(items)
                    use_claude = random.random() < (0.8 if heavy else 0.4)
                    model = (
                        enums.ModelKind.CLAUDE
                        if use_claude
                        else enums.ModelKind.OLLAMA
                    )
                    version = random.choice(
                        _CLAUDE_VERSIONS if use_claude else _OLLAMA_VERSIONS
                    )
                    item = m.Item(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        watch_id=w.id,
                        run_id=run.id,
                        source=w.source,
                        external_id=f"{w.source.value}-{seq}",
                        raw_payload={"title": summary[:60], "seq": seq},
                        content_hash=_hash(user.id, w.source, seq, summary),
                        embedding=_vector(),
                        embedding_model="nomic-embed-text",
                        fetched_at=started,
                    )
                    items.append(item)

                    confidence = round(random.uniform(0.55, 0.98), 3)
                    analysis = m.Analysis(
                        id=uuid.uuid4(),
                        item_id=item.id,
                        prompt_id=prompt_id,
                        model_used=model,
                        model_version=version,
                        params={"temperature": 0.2},
                        result=summary,
                        confidence=confidence,
                        created_at=finished,
                    )
                    analyses.append(analysis)

                    relevance = round(
                        random.uniform(0.7, 0.97)
                        if long_hit
                        else random.uniform(0.15, 0.6),
                        3,
                    )
                    # Low-confidence or borderline analyses go to review.
                    needs_review = confidence < 0.68 or random.random() < 0.18
                    eval_status = (
                        enums.EvalStatus.REVIEW
                        if needs_review
                        else enums.EvalStatus.APPROVED
                    )
                    evaluation = m.Evaluation(
                        id=uuid.uuid4(),
                        analysis_id=analysis.id,
                        relevance_score=relevance,
                        confidence=confidence,
                        status=eval_status,
                        evaluated_at=finished,
                    )
                    evaluations.append(evaluation)
                    if eval_status == enums.EvalStatus.REVIEW:
                        review_targets.append(evaluation)

                    # Cost ledger entry for the analysis.
                    if model == enums.ModelKind.CLAUDE:
                        tokens_in = random.randint(800, 4000)
                        tokens_out = random.randint(200, 1200)
                        cost = round(
                            (tokens_in * 3 + tokens_out * 15)
                            / 1_000_000
                            * (6 if heavy else 1),
                            6,
                        )
                    else:
                        tokens_in = random.randint(500, 2500)
                        tokens_out = random.randint(150, 800)
                        cost = 0.0
                    cost_events.append(
                        m.CostEvent(
                            id=uuid.uuid4(),
                            user_id=user.id,
                            run_id=run.id,
                            model=model,
                            tokens_in=tokens_in,
                            tokens_out=tokens_out,
                            cost_usd=cost,
                            created_at=finished,
                        )
                    )

                    # Notifications: only reasonably relevant, approved items
                    # are actually notified. A dashboard row plus, for some,
                    # email/webhook rows in mixed delivery states.
                    if (
                        eval_status == enums.EvalStatus.APPROVED
                        and relevance >= 0.6
                    ):
                        dedup = _hash(item.content_hash)[:24]
                        notifications.append(
                            m.Notification(
                                id=uuid.uuid4(),
                                user_id=user.id,
                                analysis_id=analysis.id,
                                channel=enums.NotificationChannel.DASHBOARD,
                                dedup_key=dedup,
                                status=enums.NotificationStatus.SENT,
                                delivered_at=finished,
                                attempts=0,
                            )
                        )
                        # Extra channels for users who enabled them, in a
                        # mix of sent / retrying / dead-lettered states.
                        for chan in (
                            enums.NotificationChannel.EMAIL,
                            enums.NotificationChannel.WEBHOOK,
                        ):
                            if random.random() < 0.5:
                                continue
                            roll = random.random()
                            if roll < 0.6:
                                st = enums.NotificationStatus.SENT
                                delivered = finished
                                attempts = 0
                            elif roll < 0.85:
                                st = enums.NotificationStatus.PENDING
                                delivered = None
                                attempts = random.randint(1, 3)
                            else:
                                st = enums.NotificationStatus.FAILED
                                delivered = None
                                attempts = 5
                            notifications.append(
                                m.Notification(
                                    id=uuid.uuid4(),
                                    user_id=user.id,
                                    analysis_id=analysis.id,
                                    channel=chan,
                                    dedup_key=dedup,
                                    status=st,
                                    delivered_at=delivered,
                                    attempts=attempts,
                                )
                            )

        session.add_all(runs)
        session.flush()
        session.add_all(items)
        session.flush()
        session.add_all(analyses)
        session.flush()
        session.add_all(evaluations + notifications + cost_events)
        session.flush()

        # --- review decisions on about half of the review-queue items ---
        decisions = []
        random.shuffle(review_targets)
        for ev in review_targets[: len(review_targets) // 2]:
            verdict = random.choice(
                [
                    enums.ReviewDecision.APPROVED,
                    enums.ReviewDecision.REJECTED,
                    enums.ReviewDecision.CORRECTED,
                ]
            )
            decisions.append(
                m.ReviewDecision(
                    id=uuid.uuid4(),
                    evaluation_id=ev.id,
                    reviewer_id=admin_id,
                    decision=verdict,
                    corrected_label=(
                        "not_relevant"
                        if verdict == enums.ReviewDecision.CORRECTED
                        else None
                    ),
                    note="Reviewed during triage.",
                    decided_at=now
                    - datetime.timedelta(hours=random.randint(1, 72)),
                )
            )
        session.add_all(decisions)

        # --- a few audit entries ---
        session.add_all(
            [
                m.AuditLogEntry(
                    id=uuid.uuid4(),
                    actor_user_id=admin_id,
                    action="user.login",
                    entity_type="user",
                    entity_id=admin_id,
                    meta={"ip": "127.0.0.1"},
                ),
                m.AuditLogEntry(
                    id=uuid.uuid4(),
                    actor_user_id=users["demo@pulsegraph.dev"].id,
                    action="watch.create",
                    entity_type="watch",
                    entity_id=watches[0].id,
                    meta={"source": watches[0].source.value},
                ),
                m.AuditLogEntry(
                    id=uuid.uuid4(),
                    actor_user_id=admin_id,
                    action="source.auto_resume",
                    entity_type="source_health",
                    entity_id=None,
                    meta={"source": "entsoe"},
                ),
            ]
        )

        session.commit()

        print(
            "Seeded: "
            f"{len(users)} users, {len(watches)} watches, {len(runs)} runs, "
            f"{len(items)} items, {len(analyses)} analyses, "
            f"{len(evaluations)} evaluations "
            f"({len(review_targets)} in review, {len(decisions)} decided), "
            f"{len(notifications)} notifications, "
            f"{len(cost_events)} cost events."
        )
        print(
            "Logins — user: demo@pulsegraph.dev / demo1234 · "
            "admin: admin@pulsegraph.dev / admin1234 "
            "(also alice/bob/carol @pulsegraph.dev, password <name>1234)."
        )


if __name__ == "__main__":
    seed()

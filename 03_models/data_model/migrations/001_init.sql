-- PetroPID-Agent 关系型数据模型 DDL (兼容 PostgreSQL 15+ / SQLite 3.35+)
-- 覆盖：控制回路主数据、时序遥测、诊断记录、辨识模型、整定任务、安全校验审计

CREATE TABLE IF NOT EXISTS control_loops (
    loop_id          VARCHAR(32) PRIMARY KEY,
    tag_name         VARCHAR(32) NOT NULL UNIQUE,
    unit_name        VARCHAR(64) NOT NULL,
    loop_type        VARCHAR(24) NOT NULL CHECK (loop_type IN ('Temperature', 'Pressure', 'Flow', 'Level')),
    description      TEXT,
    pv_unit          VARCHAR(16) NOT NULL,
    init_kc          DOUBLE PRECISION NOT NULL,
    init_ti          DOUBLE PRECISION NOT NULL,
    init_td          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    op_min           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    op_max           DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loop_telemetry (
    telemetry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    loop_id          VARCHAR(32) NOT NULL,
    timestamp_s      DOUBLE PRECISION NOT NULL,
    sp               DOUBLE PRECISION NOT NULL,
    pv               DOUBLE PRECISION NOT NULL,
    op               DOUBLE PRECISION NOT NULL CHECK (op >= 0.0 AND op <= 100.0),
    err              DOUBLE PRECISION NOT NULL,
    FOREIGN KEY (loop_id) REFERENCES control_loops(loop_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_telemetry_loop_time ON loop_telemetry(loop_id, timestamp_s);

CREATE TABLE IF NOT EXISTS diagnosis_records (
    diag_id          VARCHAR(40) PRIMARY KEY,
    loop_id          VARCHAR(32) NOT NULL,
    anomaly_type     VARCHAR(32) NOT NULL,
    severity         VARCHAR(16) NOT NULL CHECK (severity IN ('HEALTHY', 'WARNING', 'CRITICAL')),
    confidence       DOUBLE PRECISION NOT NULL,
    harris_index     DOUBLE PRECISION NOT NULL,
    oscillation_idx  DOUBLE PRECISION NOT NULL,
    stiction_index   DOUBLE PRECISION NOT NULL,
    iae              DOUBLE PRECISION NOT NULL,
    overshoot_pct    DOUBLE PRECISION NOT NULL,
    needs_retuning   BOOLEAN NOT NULL,
    needs_valve_fix  BOOLEAN NOT NULL,
    root_cause       TEXT NOT NULL,
    diagnosed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (loop_id) REFERENCES control_loops(loop_id)
);

CREATE TABLE IF NOT EXISTS identification_models (
    model_id         VARCHAR(40) PRIMARY KEY,
    loop_id          VARCHAR(32) NOT NULL,
    model_type       VARCHAR(16) NOT NULL DEFAULT 'FOPDT',
    param_k          DOUBLE PRECISION NOT NULL,
    param_tau        DOUBLE PRECISION NOT NULL,
    param_theta      DOUBLE PRECISION NOT NULL,
    train_r2         DOUBLE PRECISION NOT NULL,
    val_r2           DOUBLE PRECISION NOT NULL,
    val_accuracy_pct DOUBLE PRECISION NOT NULL,
    excitation_ok    BOOLEAN NOT NULL,
    identified_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (loop_id) REFERENCES control_loops(loop_id)
);

CREATE TABLE IF NOT EXISTS tuning_tasks (
    task_id          VARCHAR(40) PRIMARY KEY,
    loop_id          VARCHAR(32) NOT NULL,
    diag_id          VARCHAR(40),
    model_id         VARCHAR(40),
    strategy         VARCHAR(24) NOT NULL,
    rec_kc           DOUBLE PRECISION NOT NULL,
    rec_ti           DOUBLE PRECISION NOT NULL,
    rec_td           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    harris_imp_pct   DOUBLE PRECISION,
    oi_red_pct       DOUBLE PRECISION,
    iae_red_pct      DOUBLE PRECISION,
    final_status     VARCHAR(40) NOT NULL,
    elapsed_s        DOUBLE PRECISION NOT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (loop_id) REFERENCES control_loops(loop_id),
    FOREIGN KEY (diag_id) REFERENCES diagnosis_records(diag_id),
    FOREIGN KEY (model_id) REFERENCES identification_models(model_id)
);

CREATE TABLE IF NOT EXISTS safety_audit_logs (
    audit_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id          VARCHAR(40) NOT NULL,
    constraint_id    VARCHAR(16) NOT NULL,
    category         VARCHAR(32) NOT NULL,
    rule_name        VARCHAR(64) NOT NULL,
    measured_value   DOUBLE PRECISION NOT NULL,
    threshold_expr   VARCHAR(32) NOT NULL,
    passed           BOOLEAN NOT NULL,
    violation_tag    VARCHAR(64),
    evidence         TEXT,
    checked_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tuning_tasks(task_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_safety_task ON safety_audit_logs(task_id);

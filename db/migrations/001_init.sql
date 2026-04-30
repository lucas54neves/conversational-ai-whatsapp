-- TACO foods (~600 typical Brazilian items)
CREATE TABLE IF NOT EXISTS taco_foods (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    calories    NUMERIC(7,2),
    protein     NUMERIC(6,2),
    carbs       NUMERIC(6,2),
    fat         NUMERIC(6,2)
);

CREATE INDEX IF NOT EXISTS taco_foods_name_fts_idx
    ON taco_foods USING GIN (to_tsvector('portuguese', name));

-- User profile and calculated targets
CREATE TABLE IF NOT EXISTS users (
    phone_number    TEXT PRIMARY KEY,
    weight_kg       NUMERIC(5,2),
    height_cm       INT,
    age             INT,
    sex             TEXT CHECK (sex IN ('M', 'F')),
    goal            TEXT CHECK (goal IN ('lose', 'maintain', 'gain')),
    target_calories NUMERIC(7,2),
    target_protein  NUMERIC(6,2),
    target_carbs    NUMERIC(6,2),
    target_fat      NUMERIC(6,2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Meal log
CREATE TABLE IF NOT EXISTS meal_logs (
    id           SERIAL PRIMARY KEY,
    phone_number TEXT REFERENCES users(phone_number),
    food_name    TEXT NOT NULL,
    taco_food_id INT REFERENCES taco_foods(id),
    quantity_g   NUMERIC(6,1),
    calories     NUMERIC(7,2),
    protein      NUMERIC(6,2),
    carbs        NUMERIC(6,2),
    fat          NUMERIC(6,2),
    logged_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS meal_logs_phone_date_idx
    ON meal_logs (phone_number, logged_at);

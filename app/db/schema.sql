-- Расширение для ускорения fuzzy-поиска
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Проекты
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    project_code VARCHAR(128) NOT NULL UNIQUE
);

-- Шкафы, принадлежат проектам
CREATE TABLE IF NOT EXISTS cabinets (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    cabinet_code VARCHAR(128) NOT NULL
);

-- Этапы (без времени, время хранится в позициях)
CREATE TABLE IF NOT EXISTS stages (
    id SERIAL PRIMARY KEY,
    stage_name VARCHAR(128) NOT NULL UNIQUE
);

-- Виды номенклатуры, связаны с этапами
CREATE TABLE IF NOT EXISTS nomenclature_types (
    id SERIAL PRIMARY KEY,
    type_name VARCHAR(256) NOT NULL UNIQUE,
    stage_id INTEGER NOT NULL REFERENCES stages(id) ON DELETE RESTRICT
);

-- Позиции с уникальным артикулом и временем
CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    cabinet_id INTEGER NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE,
    nomenclature_type_id INTEGER NOT NULL REFERENCES nomenclature_types(id) ON DELETE RESTRICT,
    article VARCHAR(128) NOT NULL,
    name TEXT NOT NULL,
    name_norm TEXT,
    assembly_time_minutes INTEGER NOT NULL
);

-- Уникальность шкафов в рамках проекта
CREATE UNIQUE INDEX IF NOT EXISTS idx_cabinets_project_code ON cabinets(project_id, cabinet_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_article ON items(article);
CREATE INDEX IF NOT EXISTS idx_items_name_norm ON items(name_norm);
CREATE INDEX IF NOT EXISTS idx_items_cabinet_id ON items(cabinet_id);

CREATE INDEX IF NOT EXISTS idx_items_name_trgm ON items USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_items_name_norm_trgm ON items USING gin (name_norm gin_trgm_ops);

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

-- Этапы (числовое значение, ~10 вариантов)
CREATE TABLE IF NOT EXISTS stages (
    id SERIAL PRIMARY KEY,
    stage_code INTEGER NOT NULL UNIQUE,
    stage_name VARCHAR(128) NOT NULL
);

-- Виды номенклатуры, связаны с этапами
CREATE TABLE IF NOT EXISTS nomenclature_types (
    id SERIAL PRIMARY KEY,
    type_code INTEGER NOT NULL,
    type_name VARCHAR(256) NOT NULL,
    stage_id INTEGER NOT NULL REFERENCES stages(id) ON DELETE RESTRICT,
    UNIQUE(type_code, type_name)
);

-- Операции, связаны с видом номенклатуры и наименованием
CREATE TABLE IF NOT EXISTS operations (
    id SERIAL PRIMARY KEY,
    nomenclature_type_id INTEGER NOT NULL REFERENCES nomenclature_types(id) ON DELETE RESTRICT,
    operation_code INTEGER NOT NULL,
    operation_name VARCHAR(256) NOT NULL,
    time_template_minutes INTEGER NOT NULL,
    UNIQUE(nomenclature_type_id, operation_code, operation_name)
);

-- Позиции с уникальным артикулом
CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    cabinet_id INTEGER NOT NULL REFERENCES cabinets(id) ON DELETE CASCADE,
    nomenclature_type_id INTEGER NOT NULL REFERENCES nomenclature_types(id) ON DELETE RESTRICT,
    operation_id INTEGER NOT NULL REFERENCES operations(id) ON DELETE RESTRICT,
    article VARCHAR(128) NOT NULL,
    name TEXT NOT NULL,
    name_norm TEXT,
    quantity_per_unit INTEGER NOT NULL DEFAULT 1,
    total_quantity INTEGER NOT NULL DEFAULT 1
);

-- Уникальность шкафов в рамках проекта
CREATE UNIQUE INDEX IF NOT EXISTS idx_cabinets_project_code ON cabinets(project_id, cabinet_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_article ON items(article);
CREATE INDEX IF NOT EXISTS idx_items_name_norm ON items(name_norm);
CREATE INDEX IF NOT EXISTS idx_items_cabinet_id ON items(cabinet_id);
CREATE INDEX IF NOT EXISTS idx_items_nomenclature_type_id ON items(nomenclature_type_id);
CREATE INDEX IF NOT EXISTS idx_items_operation_id ON items(operation_id);
CREATE INDEX IF NOT EXISTS idx_nomenclature_types_code ON nomenclature_types(type_code);
CREATE INDEX IF NOT EXISTS idx_operations_code ON operations(operation_code);

-- Индексы для быстрого fuzzy-поиска
CREATE INDEX IF NOT EXISTS idx_items_name_trgm ON items USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_items_name_norm_trgm ON items USING gin (name_norm gin_trgm_ops);

-- Составной индекс для поиска операций по виду номенклатуры и наименованию
CREATE INDEX IF NOT EXISTS idx_operations_nomenclature_name ON operations(nomenclature_type_id, operation_name);

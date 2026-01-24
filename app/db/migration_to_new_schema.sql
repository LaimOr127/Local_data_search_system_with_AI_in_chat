-- Миграция к новой схеме БД
-- ВНИМАНИЕ: Этот скрипт удаляет все существующие данные!
-- Выполняйте только на пустой БД или после резервного копирования!

-- Удаляем старые таблицы (если они существуют)
DROP TABLE IF EXISTS items CASCADE;
DROP TABLE IF EXISTS nomenclature_types CASCADE;
DROP TABLE IF EXISTS stages CASCADE;
DROP TABLE IF EXISTS cabinets CASCADE;
DROP TABLE IF EXISTS projects CASCADE;

-- Применяем новую схему
\i app/db/schema.sql

-- Или выполните вручную:
-- psql -d assembly -f app/db/schema.sql

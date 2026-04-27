# Franklin Variant Crawler

Автоматизированная система сбора, актуализации и хранения данных о генетических вариантах с платформы Franklin (Genoox).

Проект реализует ETL-пайплайн для автоматического получения информации о вариантах по заданным генам, проверки актуальности данных, дедупликации и сохранения структурированных записей в базу данных.

---

# Возможности

## Сбор данных из Franklin API
Получение информации о вариантах по координатам:

- Genomic coordinates (`chr`, `pos`, `ref`, `alt`)
- HGVS нотации (`c_dot`, `p_dot`)
- Transcript
- Pathogenicity classification:
  - VUS
  - Likely Pathogenic
  - Pathogenic
- ACMG criteria
- Score / Bayes score

---

## Режимы работы

### Fill
Первичное заполнение базы.

```bash
python main.py fill BRCA1 BRCA2 ATM
```

---

### Update
Обновление только изменившихся вариантов.

```bash
python main.py update BRCA1
```

---

### Check
Проверка расхождений между локальной БД и Franklin API.

```bash
python main.py check CHEK2
```

---

# Структура проекта

```text
.
├── api/
│   └── api_franklin.py
│
├── db/
│   ├── domain.py
│   └── repositories.py
│
├── webcrowler/
│   ├── crowler.py
│   └── schedule.py
│
├── datamap/
│
├── input/
├── processed/
├── tests/
│
├── main.py
└── utils.py
```

---

# Используемые технологии

## Python libraries

- requests
- SQLAlchemy
- sqlite3
- argparse
- logging
- csv
- datetime
- subprocess

## Testing

- pytest

## Database

- SQLite

---
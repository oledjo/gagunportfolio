# Portfolio Sync API

Приложение для синхронизации портфеля из IntelliInvest Excel файлов в локальную SQLite базу данных с REST API.

## Структура проекта

```
project/
  main.py              # CLI точка входа для синхронизации
  api.py               # FastAPI приложение с REST endpoints
  run_api.py           # Скрипт для запуска API сервера
  models.py            # SQLModel модели (Holding)
  schemas.py           # Pydantic схемы для API
  database.py          # Настройка SQLite и сессий
  intellinvest_sync.py # Функции парсинга Excel и синхронизации
  requirements.txt     # Зависимости проекта
```

## Установка

1. Создайте виртуальное окружение:
```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Использование

### CLI синхронизация

Синхронизация портфеля из Excel файла через командную строку:

```bash
python main.py portfolio.xlsx
```

Результат:
```json
{
  "status": "success",
  "count": 156,
  "as_of": "2025-11-27T23:16:59.577550",
  "source": "intellinvest"
}
```

### REST API

Запуск API сервера:

```bash
python run_api.py
```

Сервер запустится на `http://localhost:8000`

#### Доступные endpoints:

1. **GET /** - Информация об API
2. **GET /holdings** - Получить все позиции
   - Параметры:
     - `skip` (int): пропустить N записей (пагинация)
     - `limit` (int): максимум записей (по умолчанию 100)
     - `asset_type` (str): фильтр по типу актива (stock, bond, crypto, etc.)
     - `currency` (str): фильтр по валюте (RUB, USD, EUR)
     - `ticker` (str): поиск по тикеру (частичное совпадение)
   
   Пример:
   ```bash
   curl "http://localhost:8000/holdings?limit=10&asset_type=stock"
   ```

3. **GET /holdings/{ticker}** - Получить позицию по тикеру
   
   Пример:
   ```bash
   curl "http://localhost:8000/holdings/LRN"
   ```

4. **GET /stats** - Статистика портфеля
   
   Возвращает:
   - Общее количество позиций
   - Общая стоимость покупок и текущая стоимость
   - Общий PnL (прибыль/убыток)
   - Разбивка по типам активов и валютам
   
   Пример:
   ```bash
   curl "http://localhost:8000/stats"
   ```

5. **POST /sync** - Синхронизация портфеля из загруженного Excel файла
   
   Пример:
   ```bash
   curl -X POST "http://localhost:8000/sync" \
        -F "file=@portfolio.xlsx"
   ```

6. **POST /sync/path** - Синхронизация из пути к файлу (для разработки)
   
   Пример:
   ```bash
   curl -X POST "http://localhost:8000/sync/path?path=portfolio.xlsx"
   ```

### Интерактивная документация

FastAPI автоматически генерирует интерактивную документацию:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Модель данных

### Holding

- `id` (int): Уникальный идентификатор
- `as_of` (datetime): Дата/время синхронизации
- `source` (str): Источник данных (intellinvest)
- `ticker` (str): Тикер инструмента
- `name` (str): Название инструмента
- `qty` (float): Количество
- `avg_price` (float): Средняя цена покупки
- `invested_value` (float): Стоимость покупок
- `current_value` (float): Текущая стоимость
- `pnl_value` (float): Прибыль/убыток (абсолютное значение)
- `pnl_pct` (float): Прибыль/убыток (%)
- `share_pct` (float): Доля в портфеле (%)
- `asset_type` (str): Тип актива (stock, bond, crypto, etc.)
- `currency` (str): Валюта (RUB, USD, EUR)

## База данных

SQLite база данных создается автоматически в файле `portfolio.db` при первом запуске синхронизации.

## Формат Excel файла

Приложение ожидает Excel файл, экспортированный из IntelliInvest, с листом "Все бумаги" (sheet name: "Все бумаги").

## Примеры использования

### Получить все акции в USD:
```bash
curl "http://localhost:8000/holdings?asset_type=stock&currency=USD"
```

### Получить статистику по криптовалютам:
```bash
curl "http://localhost:8000/holdings?asset_type=asset&limit=100" | \
  python3 -c "import sys, json; \
  data = json.load(sys.stdin); \
  crypto = [h for h in data if h['ticker'] in ['BTC', 'ETH', 'TON']]; \
  print(json.dumps(crypto, indent=2, ensure_ascii=False))"
```

### Синхронизация и получение статистики:
```bash
# Синхронизация
curl -X POST "http://localhost:8000/sync" -F "file=@portfolio.xlsx"

# Получение статистики
curl "http://localhost:8000/stats"
```


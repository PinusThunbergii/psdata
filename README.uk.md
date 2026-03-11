# psdata

Типізована Python-бібліотека для читання файлів PicoScope 6 `.psdata` та `.pssettings`.

Мовні версії:
- Англійська: `README.md`
- Українська: цей файл

Специфікація формату:
- Англійська: `docs/FORMAT.en.md`
- Українська: `docs/FORMAT.uk.md`

Довідник API:
- Англійська: `docs/API.en.md`
- Українська: `docs/API.uk.md`

## Можливості

- Парсинг заголовка контейнера PS6 та metadata-блоків.
- Декодування `settings.xml` для `binaryversion=0` і `binaryversion=2`.
- Типізовані моделі для вікон, каналів, налаштувань, семплів і math-каналів.
- Потокова ітерація семплів (`iter_channel_samples`, `samples`).
- Попередньо обчислені NumPy API (`samples_np`, `channels_np`, `math_np`, `fft_np`).
- Експорт декодованих артефактів і CSV-підсумків (`psdata-export` CLI).
- Повний доступ до XML (`ElementTree` + перетворення у словник).

## Встановлення

### Через `uv` (рекомендовано)

```bash
uv sync
uv sync --extra numpy
```

### Через `pip`

```bash
pip install .
pip install .[numpy]
```

## Швидкий старт

```python
from psdata import PsData

ps = PsData.open("1.psdata")
print(ps.windows_count())

for ch in ps.channels(window_index=0):
    print(ch.channel_index, ch.name, ch.enabled, ch.unit_type)

cfg = ps.channel_settings(channel=0, window_index=0)
print(cfg.sample_rate_hz, cfg.coupling)

for s in ps.samples(channel=0, window_index=0, step=10):
    print(s.sample_index, s.time_seconds, s.adc_raw)
    break
```

## NumPy API

Потрібен `numpy` (`pip install .[numpy]`).

```python
from psdata import PsData

ps = PsData.open("1.psdata")

ch = ps.samples_np(channel=0, window_index=0, buffer_index=0, value_mode="scaled")
print(ch.values.shape, ch.values.dtype)

all_channels = ps.channels_np(window_index=0, buffer_index=0, value_mode="scaled")
print(list(all_channels.keys()))

m = ps.math_np(index=0, window_index=0, buffer_index=0)
print(m.formula, m.values.shape)

spec = ps.fft_np(channel=0, window_index=0, buffer_index=0, window_fn="hann", detrend="mean")
print(spec.sample_rate_hz, spec.frequency_hz.shape, spec.magnitude.shape)
```

## Приклади

Окремі приклади знаходяться в `examples/`:
- `basic_usage.py`
- `numpy_usage.py`
- `export_usage.py`

Запуск із кореня репозиторію:

```bash
uv run python examples/basic_usage.py 1.psdata
uv run python examples/numpy_usage.py 1.psdata --step 500
uv run python examples/export_usage.py 1.psdata --out 1.psdata.decoded.example
```

## CLI

Після встановлення:

```bash
psdata-export 1.psdata --out 1.psdata.decoded
```

## Збірка і пакування

Збірка sdist + wheel:

```bash
uv build
```

Результат:
- `dist/*.tar.gz`
- `dist/*.whl`

Додаткова перевірка:

```bash
uv run python -m pip install twine
uv run python -m twine check dist/*
```

## Що реалізовано

- Базовий парсинг контейнера `.psdata/.pssettings`.
- Декодування metadata-блоку `kq`.
- Декодування binary payload (`none`, `gzip`, `binaryversion=2` transform).
- Витяг семплів каналів з відновленням часової осі.
- Наближений перерахунок у фізичні значення на основі XML-конфігурації каналу.
- Метадані math-каналів і скалярне обчислення формул підтриманого підмножинного синтаксису.
- NumPy API з FFT для фізичних або обчислених math-даних.

## Що поки не реалізовано

- Нативне виконання `FFT(...)` безпосередньо всередині `mathsformula`.
- Повна сумісність з усіма внутрішніми типами формул/функцій PicoScope.
- Розширені спектральні режими (усереднення, PSD-одиниці, vendor-specific нормалізація FFT).
- Гарантована підтримка майбутніх невідомих `binaryversion` і нових compression-варіантів.

## Важливі нюанси

- `approx_scaled_value` обчислюється лінійно з XML-діапазонів і може відрізнятися від значень UI PicoScope у деяких режимах проб/пристроїв.
- `channel_settings().sample_rate_hz` визначається за timing metadata (спочатку per-channel timechunk, потім fallback на samplingconfig).
- Часові сітки каналів можуть відрізнятися; багатоканальні операції вирівнюються за спільним `sample_index`.
- `fft_np()` оцінює sample rate через медіану позитивних `dt`; нерівномірна сітка часу впливає на інтерпретацію спектра.
- Для великих захоплень `*_np` методи можуть споживати багато пам'яті.

## Публічний API

Основні експорти з `psdata`:
- `PsData`, `PsDataDocument`, `PsDataError`
- `Header`, `MetadataInfo`, `ParsedContainer`, `KnownChunk`, `BinaryDescriptor`
- `ChannelInfo`, `ChannelSettings`, `ChannelFilterSettings`, `ChannelSample`, `WindowInfo`
- `MathChannelInfo`, `MathChannelSample`
- `ValueMode`, `ChannelArray`, `MathChannelArray`, `SpectrumArray`
- `samples_np`, `channels_np`, `math_np`, `fft_np`
- `open_psdata`, `read_known_chunks`, `element_to_dict`
- `export_settings_csvs`, `export_channel_data`, `run`

## Ліцензія

WTFPL (див. `LICENSE`).

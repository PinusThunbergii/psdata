# Довідник API `psdata` (Українська)

Ця сторінка описує основні публічні функції та класи, які експортує `psdata`.

## Імпорти

```python
from psdata import (
    PsData,
    PsDataDocument,
    PsDataError,
    open_psdata,
    samples_np,
    channels_np,
    math_np,
    fft_np,
    run,
    export_settings_csvs,
    export_channel_data,
)
```

## 1) High-Level API (`PsData`)

### `PsData.open(path: str | Path) -> PsData`
Відкриває `.psdata` / `.pssettings` і повертає high-level фасад.

### `windows_count() -> int`
Повертає кількість capture-вікон у `settings.xml`.

### `windows_info(include_channels: bool = True) -> list[WindowInfo]`
Повертає структуровану інформацію по вікнах:
- `window_type`, `buffer_count`, `channels_count`
- `enabled_channels_count`, `maths_channels_count`
- опційно список каналів

### `channels(window_index: int = 0, enabled_only: bool = False) -> list[ChannelInfo]`
Повертає описи каналів для вікна.

### `channel_settings(channel: int, window_index: int = 0) -> ChannelSettings`
Повертає деталізовані налаштування каналу:
- probe/range/ADC поля
- `bandwidth_limit`
- `sample_rate_hz` (обчислюється з time metadata)

### `samples(...) -> Iterator[ChannelSample]`
Потокова ітерація семплів з фільтрами:
- `channel`
- `window_index`
- `buffer_index`
- `step`

### `samples_map(...) -> dict[int, Iterator[ChannelSample]]`
Мапа `channel_index -> iterator` для вибраного вікна.

### Math-канали

#### `has_math_channels(window_index: int = 0) -> bool`
Швидка перевірка наявності math-каналів.

#### `math_channels(window_index: int = 0) -> list[MathChannelInfo]`
Повертає всі math-визначення з channel repository.

#### `math_channel(index: int, window_index: int = 0) -> MathChannelInfo`
Повертає один math-канал за індексом у списку.

#### `eval_math_channel(...) -> Iterator[MathChannelSample]`
Обчислює підтримані скалярні формули на вирівняних `sample_index`.

Підтримуваний підмножинний синтаксис:
- посилання `#N`
- `+ - * / ^`, унарні `+/-`, дужки
- константи `pi`, `e`
- функції: `abs`, `sqrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log`, `log10`, `floor`, `ceil`, `round`, `min`, `max`

Не підтримується:
- `FFT(...)` всередині тексту формули

#### `eval_math_channel_rows(...) -> Iterator[dict[str, Any]]`
Те саме, але як словники.

### NumPy-методи на `PsData`

#### `samples_np(...) -> ChannelArray`
Попередньо обчислені масиви для одного каналу.

#### `channels_np(...) -> dict[int, ChannelArray]`
Попередньо обчислені масиви для кількох каналів.

#### `math_np(...) -> MathChannelArray`
Попередньо обчислені масиви для одного math-каналу.

#### `fft_np(...) -> SpectrumArray`
FFT-спектр (частота + амплітуда) із джерела:
- `channel=<int>`
- `math_index=<int>`

Потрібно передати рівно одне джерело.

## 2) Dot-Path доступ до XML (`XmlAccessor`)

`PsData.settings` і `PsData.metadata` мають:

### `node(path: str) -> Optional[Element]`
Повертає XML-вузол за dot-шляхом.

### `get(path: str, default: Optional[str] = None, attr: str = "value") -> Optional[str]`
Повертає атрибут (або текст) за dot-шляхом.

Приклади:
- `capturewindows.capturewindow.0.capturewindowtype`
- `capturewindows.0.capturewindowtype`

## 3) Low-Level API (`PsDataDocument`)

Створення:
- `open_psdata(path)`
- або `PsData.open(path).document`

### XML і metadata
- `metadata_xml_text`, `settings_xml_text`
- `metadata_dict()`, `settings_dict()`
- `find_metadata(path)`, `find_settings(path)`
- `get_metadata_value(path, attr="value", default=None)`
- `get_settings_value(path, attr="value", default=None)`

### Binary descriptors і chunks
- `iter_binary_nodes()`
- `iter_binary_descriptors()`
- `decode_binary_node(binary_node)`
- `decode_binary_descriptor(descriptor)`
- `known_chunks()`

### Семпли і summary
- `iter_channel_samples(step=1)`
- `iter_channel_rows(step=1)`
- `summary()`

## 4) NumPy-функції рівня модуля

Ці функції експортуються з `psdata` і еквівалентні методам `PsData`:
- `samples_np(ps, ...)`
- `channels_np(ps, ...)`
- `math_np(ps, ...)`
- `fft_np(ps, ...)`

Зручно для функціонального стилю.

## 5) Export API і CLI

### `run(input_file, out_dir, extract_channel_series=True, channel_step=1) -> dict`
Основний експортний pipeline:
- записує `metadata.xml`, `settings.xml`
- створює CSV-підсумки
- опційно створює per-sample CSV по каналах
- витягає відомі trailer chunks
- записує `summary.json`

### `export_settings_csvs(settings_xml, out_dir) -> dict`
Записує:
- `capture_windows.csv`
- `channels.csv`
- `channel_repository.csv`

### `export_channel_data(settings_xml, data, header, out_dir, step=1) -> dict`
Записує per-channel CSV із семплами.

### CLI entry point

```bash
psdata-export input.psdata --out input.psdata.decoded
```

## 6) Помилки

### `PsDataError`
Викидається для невалідних/непідтриманих випадків, зокрема:
- неочікувані значення заголовка/сигнатури
- невідомий `binaryversion` або compression mode
- індекс каналу/вікна/math-каналу поза діапазоном
- непідтримані конструкції math-виразів
- відсутні потрібні source-семпли для формули

## 7) Мінімальні приклади

```python
from psdata import PsData

ps = PsData.open("1.psdata")
print(ps.windows_count())
print(ps.channels(window_index=0))
print(ps.channel_settings(channel=0).sample_rate_hz)
```

```python
from psdata import PsData

ps = PsData.open("1.psdata")
spec = ps.fft_np(channel=0, window_index=0, buffer_index=0, step=500)
print(spec.frequency_hz.shape, spec.magnitude.shape)
```

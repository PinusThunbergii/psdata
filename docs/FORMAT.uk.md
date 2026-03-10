# Формат PSDATA (Українська)

Цей документ описує формат `.psdata/.pssettings` у межах поточної реалізації бібліотеки та висновків з reverse-engineering бінарників PicoScope 6.

## 1. Заголовок контейнера

На початку файлу:
1. `uint32` сигнатура: `0x4457574A`
2. `uint32` маркер типу файлу:
   - data: `0x049BA5E3`
   - settings: `0x9EB3687E`
3. `int32` версія заголовка (зазвичай `1`)
4. `int64` довжина основного payload
5. `64 bytes` резерв (`8 * int64`)

Похідні поля:
- `main_payload_start = 84`
- `main_payload_end = main_payload_start + main_payload_length`

## 2. Core Metadata Block

Одразу після `main_payload_end`:
1. `uint32 CORE_MARKER = 0x45E3F55B`
2. `int64` довжина metadata XML
3. payload блоку `kq` (байти metadata XML)

Metadata XML зазвичай містить:
- `applicationversion`
- `fileguid`
- `uncompressedlength`
- `compressedlength`
- `binaryversion`

## 3. Структура блоку `kq`

Кодування `kq`:
1. `int32 isCompressed` (`0` або `1`)
2. `int64 uncompressedLength`
3. `64 bytes` резерв
4. payload:
   - gzip-байти, якщо `isCompressed=1`
   - raw-байти, якщо `isCompressed=0`

## 4. Декодування `settings.xml`

### `binaryversion=0`
- вміст settings уже доступний через metadata-шлях.

### `binaryversion=2`
- стиснений settings-блок зберігається ближче до кінця main payload.
- ланцюжок декодування:
1. зчитати `compressedlength` байт за адресою
   `main_payload_start + main_payload_length - compressedlength`
2. застосувати трансформацію Pico (`er_transform`) із seed:
   `(Int64LE(fileguid[0:8]) XOR absolute_offset XOR uncompressedlength) & 0xFFFFFFFF`
3. `gzip.decompress(...)`
4. очистити BOM/нульові хвости

## 5. Дескриптори binary-даних (`<binary>`)

У `settings.xml` value chunk посилається на binary-дані такими полями:
- `guid`
- `uncompressedlength`
- `binaryversion`
- `offset` (відносно `main_payload_start`)
- `compressiontype` (`none` або `gzip`)
- `compressedlength`

Абсолютний offset:
- `absolute_start = main_payload_start + offset`

## 6. Зберігання семплів

Семпли каналів описуються у:
- `capturewindows/capturewindow/circularBuffer/buffers/buffer/enabledchannels/enabled`

Для кожного enabled-каналу:
- `collectiontimearray/timechunk[]` (часова інформація)
- `values/valuechunk[]` (бінарні чанки)

Декодований payload valuechunk:
- little-endian signed `int16[]`

Якщо довжина payload непарна, останній байт ігнорується.

## 7. Відновлення часової осі

Для чанка `k`:
- використовується `timechunk[k]` (якщо є):
  - `start`
  - `interval`
  - `count`

Час семплу:
- `time_seconds = start + i * interval`

Глобальний індекс семплу в каналі накопичується між чанками:
- `sample_index = chunk_sample_offset + i`

## 8. ADC і масштабування

Сире значення:
- `adc_raw` з декодованого `int16`

Скориговане:
- `adc_adjusted = adc_raw - adccountszerooffset`

Наближене фізичне значення:
- лінійне перетворення через `minadccounts/maxadccounts` та `scaledrange min/max`.
- це наближення і не завжди точно збігається з UI PicoScope для всіх режимів проб/пристроїв.

## 9. Структури вікон і каналів

Ключові вузли:
- `capturewindows/capturewindow`
- `.../devicesettings/channelconfig/channels/channel`
- `.../channelrepository/mathsChannelCollection/mathsChannel`
- `.../filtermanager/channels/channel`

Вікно містить:
- тип захоплення, нотатки, reference на пристрій, буфери, репозиторій каналів.

Конфіг каналу містить:
- enable-стан, coupling, одиниці, probe-дані, ADC-ліміти, zero offset, діапазони, bandwidth limit.

## 10. Math-канали

Зберігаються в:
- `.../channelrepository/mathsChannelCollection/mathsChannel/mathsformula`

Поля:
- `formula`, `formulaname`, `formulacolour`
- `rangemin`, `rangemax`
- `unittype`, `fullname`, `shortname`, `si`

Поточний evaluator підтримує:
- посилання на канали `#0`, `#1`, ...
- `+ - * / ^`, унарні `+/-`, дужки
- константи `pi`, `e`
- функції: `abs`, `sqrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log`, `log10`, `floor`, `ceil`, `round`, `min`, `max`

Не підтримується:
- пряме виконання `FFT(...)` у formula evaluator.

## 11. Trailer-чанки

Після основних блоків можуть бути додаткові чанки:
- `preview_small.png`
- `preview_large.png`
- `reference_waveforms.bin`
- `automotive_details.xml`

Вони читаються з кінця файлу за marker/offset-правилами.

## 12. Поточні обмеження

- Реалізовані тільки відомі типи компресії (`none`, `gzip`).
- Невідомі майбутні `binaryversion` викликають `PsDataError`.
- Частина vendor-specific семантики UI визначена емпірично і не гарантується.

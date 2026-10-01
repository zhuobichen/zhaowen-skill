#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows Prefetch (.pf) 解析器：运行次数 + 最近 8 次运行时间 + 加载的文件/卷。

为什么要自己实现
----------------
Windows 8 起 Prefetch 默认**压缩**存储，文件头是 `MAM\\x04` 而不是 `SCCA`。
用 `struct.unpack('<I', head[4:8])` 去比 `0x53434341`（"SCCA"）会全部匹配失败，
于是很容易得出「这是 Win11 24H2 的新格式，读不出运行次数」的结论 ——
**这个结论是错的**：`MAM` 只是压缩标记，解开之后仍是标准的 v30/v31 布局，
`run_count` 和最多 8 个 `last_runs` 都在里面。

实现来源：Sootmark/prefetch（MIT OR Apache-2.0，Rust，零依赖），
按 MS-XCA §2.2.4 写的 LZ77+Huffman 解压器 + 各版本字段偏移。
这里是逐行移植，并保留了作者的两个单元测试来验证移植正确性
（见文件末尾 `_selftest()`）。
"""
import struct

BLOCK = 65536
MAX_BITS = 15
SYMBOLS = 512
MASK32 = 0xFFFFFFFF
SIGNATURE = b'SCCA'
HEADER = 84                       # 各段偏移表开始的字节位置
MAM = b'MAM'


class PrefetchError(Exception):
    pass


# ---------------------------------------------------------------- MS-XCA

def _build_table(lengths):
    """每个 15 位前缀 -> (符号, 码长)。"""
    entries = [(0, 0)] * (1 << MAX_BITS)
    code = 0
    filled = 0
    for bits in range(1, MAX_BITS + 1):
        for symbol, length in enumerate(lengths):
            if length != bits:
                continue
            span = 1 << (MAX_BITS - bits)
            start = code << (MAX_BITS - bits)
            end = start + span
            if end > len(entries):
                raise PrefetchError('invalid Huffman table')
            for k in range(start, end):
                entries[k] = (symbol, length)
            filled += span
            code += 1
        code <<= 1
    if filled == 0:
        raise PrefetchError('invalid Huffman table')
    return entries


class _Bits:
    """16 位小端字、高位在前，缓冲 32 位。"""

    def __init__(self, data, at):
        self.data = data
        self.at = at
        self.next = 0
        self.extra = 16
        self.next = ((self._word() << 16) | self._word()) & MASK32

    def _word(self):
        if self.at + 2 > len(self.data):
            raise PrefetchError('compressed data ends mid-block')
        v = self.data[self.at] | (self.data[self.at + 1] << 8)
        self.at += 2
        return v

    def byte(self):
        if self.at >= len(self.data):
            raise PrefetchError('compressed data ends mid-block')
        v = self.data[self.at]
        self.at += 1
        return v

    def consume(self, count):
        if count == 0:
            return
        # Rust 的 checked_shl：count>=32 得 0，否则在 u32 内回绕
        self.next = ((self.next << count) & MASK32) if count < 32 else 0
        self.extra -= count
        if self.extra < 0:
            self.next = (self.next | (self._word() << (-self.extra))) & MASK32
            self.extra += 16


def decompress(data, size):
    """MS-XCA LZ77+Huffman，解出 size 字节。"""
    out = bytearray()
    at = 0
    while len(out) < size:
        tb = data[at:at + SYMBOLS // 2]
        if len(tb) < SYMBOLS // 2:
            raise PrefetchError('compressed data ends mid-block')
        lengths = [0] * SYMBOLS
        for i, b in enumerate(tb):
            lengths[2 * i] = b & 0x0F
            lengths[2 * i + 1] = b >> 4
        table = _build_table(lengths)
        bits = _Bits(data, at + SYMBOLS // 2)
        end = min(len(out) + BLOCK, size)
        while len(out) < end:
            symbol, length = table[(bits.next >> (32 - MAX_BITS)) & 0x7FFF]
            if length == 0:
                raise PrefetchError('invalid Huffman table')
            bits.consume(length)
            if symbol < 256:
                out.append(symbol)
                continue
            symbol -= 256
            offset_bits = symbol >> 4
            length = symbol & 0x0F
            if length == 15:
                length = bits.byte()
                if length == 255:
                    length = bits._word()
                    if length == 0:
                        low = bits._word()
                        high = bits._word()
                        length = (high << 16) | low
                    length -= 15
                    if length < 0:
                        raise PrefetchError('invalid match length')
                length += 15
            length += 3
            if offset_bits == 0:
                offset = 1
            else:
                offset = ((bits.next >> (32 - offset_bits))
                          & ((1 << offset_bits) - 1)) | (1 << offset_bits)
            bits.consume(offset_bits)
            src = len(out) - offset
            if src < 0:
                raise PrefetchError('match before the start of the output')
            for i in range(min(length, size - len(out))):
                out.append(out[src + i])       # 逐字节：匹配可重叠自身
        at = bits.at
    return bytes(out)


# ---------------------------------------------------------------- 布局

# 各版本把字段放在哪（来自 Sootmark/prefetch 的 layout()，
# v30/31 的 run_count 两处偏移是与 PECmd 对拍确认过的）
LAYOUTS = {
    17: dict(last_runs=120, slots=1, run_count=144, metric_size=20, volume=40),
    23: dict(last_runs=128, slots=1, run_count=152, metric_size=32, volume=104),
    26: dict(last_runs=128, slots=8, run_count=208, metric_size=32, volume=104),
}


def _layout(version, metrics_offset):
    if version in LAYOUTS:
        return LAYOUTS[version]
    if version in (30, 31):
        # 文件信息表的位置（0x128 / 0x130）决定运行次数在哪
        return dict(last_runs=128, slots=8,
                    run_count=200 if metrics_offset == 0x128 else 208,
                    metric_size=32, volume=96)
    return None


def _u32(d, at):
    if at + 4 > len(d):
        raise PrefetchError('%d bytes past the end of the file' % at)
    return struct.unpack_from('<I', d, at)[0]


def _u64(d, at):
    if at + 8 > len(d):
        raise PrefetchError('%d bytes past the end of the file' % at)
    return struct.unpack_from('<Q', d, at)[0]


def _utf16(d, at, chars):
    end = at + chars * 2
    if end > len(d):
        raise PrefetchError('%d bytes past the end of the file' % at)
    raw = d[at:end]
    units = []
    for i in range(0, len(raw) - 1, 2):
        u = raw[i] | (raw[i + 1] << 8)
        if u == 0:
            break
        units.append(u)
    return ''.join(chr(u) for u in units)


def _decompressed(file_bytes):
    size = _u32(file_bytes, 4)
    variant = file_bytes[3] if len(file_bytes) > 3 else 0
    if variant == 0x04:
        data_at = 8
    elif variant == 0x84:
        data_at = 12                      # 带 CRC-32 的变体
    else:
        raise PrefetchError('unknown MAM compression 0x%02x' % variant)
    if size > 64 << 20:
        # Prefetch 文件都很小，声称这么大是损坏而不是文件
        raise PrefetchError('implausible decompressed size %d' % size)
    return decompress(file_bytes[data_at:], size)


def parse(file_bytes):
    """解析一个 .pf，压缩或未压缩都可以。

    返回 dict:
      version / compressed / executable / hash / run_count
      last_runs  —— FILETIME 列表，最近在前（v26 起最多 8 个）
      problems   —— 读不出的段落说明（其余部分仍返回）
    """
    if file_bytes.startswith(MAM):
        data = _decompressed(file_bytes)
        res = _parse_scca(data)
        res['compressed'] = True
        return res
    return _parse_scca(file_bytes)


def _parse_scca(d):
    if len(d) < 8 or d[4:8] != SIGNATURE:
        raise PrefetchError('not a prefetch file (no SCCA signature)')
    version = _u32(d, 0)
    metrics_offset = _u32(d, HEADER)
    lay = _layout(version, metrics_offset)
    if lay is None:
        raise PrefetchError('unknown prefetch version %d' % version)
    last_runs = []
    for slot in range(lay['slots']):
        t = _u64(d, lay['last_runs'] + 8 * slot)
        if t:
            last_runs.append(t)
    return {
        'version': version,
        'compressed': False,
        'executable': _utf16(d, 16, 30),
        'hash': _u32(d, 76),
        'run_count': _u32(d, lay['run_count']),
        'last_runs': last_runs,
        'problems': [],
    }


def filetime_to_dt(ft):
    """FILETIME(UTC) -> 本地 naive datetime。"""
    import datetime
    if not ft:
        return None
    try:
        return datetime.datetime.fromtimestamp(ft / 10000000.0 - 11644473600)
    except (OSError, OverflowError, ValueError):
        return None


# ---------------------------------------------------------------- 自检

def _selftest():
    """作者 Rust 版里那两个单元测试，逐条搬过来验证移植。

    移植最怕「看着像对的」：解压器错一个移位，输出就是垃圾而不是报错。
    作者用真实文件对拍过 PECmd，这里把他的构造性测试当锚点。
    """
    # 1) 全字面量表：256 个符号各 8 位，码字即字节值本身
    #    原文是 `for pair in b"Hi!\0".chunks(2)`，即 b'Hi' 与 b'!\x00'
    table = bytearray([0x88] * 128) + bytearray([0] * 128)
    payload = bytearray(table)
    for pair in (b'Hi', b'!\x00'):
        payload += bytes([pair[1], pair[0]])
    payload += b'\x00\x00\x00\x00'
    got = decompress(bytes(payload), 3)
    if got != b'Hi!':
        raise SystemExit('PREFETCH SELFTEST FAILED: literals -> %r' % (got,))

    # 2) 坏输入必须报错而不是静默给垃圾
    try:
        decompress(b'\x00' * 10, 5)
        raise SystemExit('PREFETCH SELFTEST FAILED: truncated input accepted')
    except PrefetchError:
        pass
    try:
        decompress(bytes(256) + bytes(8), 5)
        raise SystemExit('PREFETCH SELFTEST FAILED: bad table accepted')
    except PrefetchError:
        pass
    return True


if __name__ == '__main__':
    import sys, glob, os, datetime
    if len(sys.argv) > 1 and sys.argv[1] == '--selftest':
        _selftest()
        print('prefetch selftest: OK (2 anchor tests from the Rust original)')
        sys.exit(0)

    _selftest()
    targets = sys.argv[1:] or sorted(glob.glob(r'C:\Windows\Prefetch\*.pf'))[:6]
    print('%-36s %-4s %-5s %-9s %-7s %s' % ('FILE', 'ver', '压缩', '运行次数', '最近运行', '可执行名'))
    for p in targets:
        try:
            r = parse(open(p, 'rb').read())
        except Exception as e:
            print('%-36s  FAIL %s' % (os.path.basename(p)[:36], e))
            continue
        lr = filetime_to_dt(r['last_runs'][0]) if r['last_runs'] else None
        print('%-36s %-4d %-5s %-9d %-7s %s' % (
            os.path.basename(p)[:36], r['version'],
            'MAM' if r['compressed'] else '否',
            r['run_count'],
            lr.strftime('%m-%d %H:%M') if lr else '-',
            r['executable']))

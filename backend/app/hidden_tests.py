"""Hidden unit-test suites + precise prompts for the tasks that are gradable end-to-end.

These suites are stored in the `tasks.hidden_tests` column and are NEVER returned by the API
or placed in the agent's workspace. They are only copied into the sandbox *after* the agent has
finished, so an agent cannot read or overfit to them.

Each suite is plain Python (no pytest dependency inside the sandbox): functions named `test_*`
that `import solution` and assert. The sandbox runner counts passes/failures.
"""

SPECS: dict[str, dict[str, str]] = {}


def _spec(task_id: str, prompt: str, tests: str) -> None:
    SPECS[task_id] = {"prompt": prompt.strip(), "tests": tests.strip() + "\n"}


_spec("python-core-t01",
      "Write `is_palindrome(s: str) -> bool`. It returns True when `s` reads the same forwards and backwards, "
      "ignoring case and ignoring every non-alphanumeric character. The empty string is a palindrome.",
      '''
import solution as s

def test_simple():
    assert s.is_palindrome("racecar") is True

def test_not_palindrome():
    assert s.is_palindrome("hello") is False

def test_case_insensitive():
    assert s.is_palindrome("Madam") is True

def test_ignores_punctuation_and_spaces():
    assert s.is_palindrome("A man, a plan, a canal: Panama") is True

def test_empty_and_single():
    assert s.is_palindrome("") is True
    assert s.is_palindrome("x") is True

def test_digits_count():
    assert s.is_palindrome("12321") is True
    assert s.is_palindrome("12345") is False
''')

_spec("python-core-t06",
      "Write `binary_search(arr: list[int], target: int) -> int`. `arr` is sorted ascending and contains distinct "
      "integers. Return the index of `target`, or -1 if it is absent. Must run in O(log n).",
      '''
import solution as s

def test_found_middle():
    assert s.binary_search([1, 3, 5, 7, 9], 5) == 2

def test_found_edges():
    assert s.binary_search([1, 3, 5, 7, 9], 1) == 0
    assert s.binary_search([1, 3, 5, 7, 9], 9) == 4

def test_missing():
    assert s.binary_search([1, 3, 5, 7, 9], 4) == -1
    assert s.binary_search([1, 3, 5, 7, 9], 100) == -1

def test_empty():
    assert s.binary_search([], 1) == -1

def test_single():
    assert s.binary_search([4], 4) == 0
    assert s.binary_search([4], 5) == -1

class _Counting(list):
    """Counts element accesses so a linear scan cannot pass as O(log n)."""
    ops = 0
    def __getitem__(self, i):
        type(self).ops += 1
        return list.__getitem__(self, i)
    def __iter__(self):
        type(self).ops += len(self)
        return list.__iter__(self)
    def __contains__(self, x):
        type(self).ops += len(self)
        return list.__contains__(self, x)
    def index(self, *a):
        type(self).ops += len(self)
        return list.index(self, *a)

def test_is_logarithmic():
    arr = _Counting(range(0, 2_000_000, 2))
    _Counting.ops = 0
    assert s.binary_search(arr, 1_999_998) == 999_999
    assert s.binary_search(arr, 7) == -1
    assert _Counting.ops <= 120, "too many element accesses: %d" % _Counting.ops

def test_negative_numbers():
    assert s.binary_search([-9, -4, 0, 3], -4) == 1
''')

_spec("python-core-t07",
      "Write `merge_sorted(a: list[int], b: list[int]) -> list[int]` that merges two ascending lists into one new "
      "ascending list in O(len(a) + len(b)). Do not mutate the inputs. Duplicates are kept.",
      '''
import solution as s

def test_basic():
    assert s.merge_sorted([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]

def test_one_empty():
    assert s.merge_sorted([], [1, 2]) == [1, 2]
    assert s.merge_sorted([1, 2], []) == [1, 2]

def test_both_empty():
    assert s.merge_sorted([], []) == []

def test_duplicates_kept():
    assert s.merge_sorted([1, 1, 2], [1, 3]) == [1, 1, 1, 2, 3]

def test_does_not_mutate_inputs():
    a, b = [1, 4], [2, 3]
    s.merge_sorted(a, b)
    assert a == [1, 4] and b == [2, 3]

def test_returns_new_list():
    a = [1, 2]
    out = s.merge_sorted(a, [])
    assert out == [1, 2] and out is not a

def test_uneven_lengths():
    assert s.merge_sorted([10], [1, 2, 3, 20]) == [1, 2, 3, 10, 20]
''')

_spec("python-core-t08",
      "Write `flatten(items: list) -> list` that flattens arbitrarily nested lists into one flat list, preserving "
      "order. Only `list` objects are flattened; strings, tuples, dicts and everything else are leaves. Must not hit "
      "the recursion limit for nesting depth 5000.",
      '''
import solution as s

def test_flat_unchanged():
    assert s.flatten([1, 2, 3]) == [1, 2, 3]

def test_nested():
    assert s.flatten([1, [2, [3, [4]]], 5]) == [1, 2, 3, 4, 5]

def test_empty_sublists():
    assert s.flatten([[], [[]], 1]) == [1]

def test_strings_are_leaves():
    assert s.flatten(["ab", ["cd"]]) == ["ab", "cd"]

def test_tuples_are_leaves():
    assert s.flatten([(1, 2), [3]]) == [(1, 2), 3]

def test_deep_nesting():
    deep = []
    cur = deep
    for _ in range(5000):
        nxt = []
        cur.append(nxt)
        cur = nxt
    cur.append(7)
    assert s.flatten(deep) == [7]
''')

_spec("python-core-t11",
      "Write `is_valid(s: str) -> bool`. `s` contains only the characters ()[]{}. Return True iff every bracket is "
      "closed by the same type, in the correct order. The empty string is valid.",
      '''
import solution as s

def test_simple_pairs():
    assert s.is_valid("()") is True
    assert s.is_valid("()[]{}") is True

def test_nested():
    assert s.is_valid("{[()]}") is True

def test_wrong_type():
    assert s.is_valid("(]") is False

def test_wrong_order():
    assert s.is_valid("([)]") is False

def test_unclosed():
    assert s.is_valid("((") is False

def test_extra_closer():
    assert s.is_valid("())") is False
    assert s.is_valid(")") is False

def test_empty():
    assert s.is_valid("") is True
''')

_spec("python-core-t13",
      "Write `roman_to_int(s: str) -> int` converting a valid Roman numeral (1..3999, standard subtractive notation "
      "such as IV, IX, XL, XC, CD, CM) to an integer.",
      '''
import solution as s

def test_single():
    assert s.roman_to_int("V") == 5

def test_additive():
    assert s.roman_to_int("VIII") == 8
    assert s.roman_to_int("XXVII") == 27

def test_subtractive():
    assert s.roman_to_int("IV") == 4
    assert s.roman_to_int("IX") == 9
    assert s.roman_to_int("XL") == 40

def test_mixed():
    assert s.roman_to_int("MCMXCIV") == 1994

def test_max():
    assert s.roman_to_int("MMMCMXCIX") == 3999

def test_min():
    assert s.roman_to_int("I") == 1
''')

_spec("python-core-t14",
      "Write `transpose(m: list[list[int]]) -> list[list[int]]` returning the transpose of a rectangular matrix as a "
      "new list of lists. An empty matrix returns `[]`. Do not mutate the input.",
      '''
import solution as s

def test_square():
    assert s.transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]

def test_wide():
    assert s.transpose([[1, 2, 3], [4, 5, 6]]) == [[1, 4], [2, 5], [3, 6]]

def test_tall():
    assert s.transpose([[1], [2], [3]]) == [[1, 2, 3]]

def test_empty():
    assert s.transpose([]) == []

def test_input_not_mutated():
    m = [[1, 2], [3, 4]]
    s.transpose(m)
    assert m == [[1, 2], [3, 4]]

def test_rows_are_lists():
    out = s.transpose([[1, 2], [3, 4]])
    assert all(isinstance(r, list) for r in out)
''')

_spec("python-core-t19",
      "Write `chunk(items: list, size: int) -> list[list]` splitting `items` into consecutive groups of `size` (the "
      "last group may be shorter). Raise `ValueError` if `size <= 0`. Must work for any list, including empty.",
      '''
import solution as s

def test_even():
    assert s.chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

def test_remainder():
    assert s.chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

def test_size_larger_than_list():
    assert s.chunk([1, 2], 10) == [[1, 2]]

def test_empty():
    assert s.chunk([], 3) == []

def test_size_one():
    assert s.chunk([1, 2, 3], 1) == [[1], [2], [3]]

def test_bad_size():
    for bad in (0, -1):
        try:
            s.chunk([1], bad)
        except ValueError:
            continue
        raise AssertionError("expected ValueError")
''')


# ---------------------------------------------------------------------------
# Stage 2 expansion — additional gradable tasks across the catalogue
# ---------------------------------------------------------------------------

_spec("python-core-t02",
      "Write `fizzbuzz(n: int) -> list[str]` returning the FizzBuzz sequence from 1..n inclusive. "
      "Multiples of 3 → 'Fizz', of 5 → 'Buzz', of both → 'FizzBuzz', else the number as a string. "
      "Raise ValueError if n < 1.",
      '''
import solution as s

def test_basic():
    assert s.fizzbuzz(5) == ["1", "2", "Fizz", "4", "Buzz"]

def test_fizzbuzz():
    assert s.fizzbuzz(15)[-1] == "FizzBuzz"

def test_one():
    assert s.fizzbuzz(1) == ["1"]

def test_bad():
    for n in (0, -3):
        try:
            s.fizzbuzz(n)
        except ValueError:
            continue
        raise AssertionError("expected ValueError")
''')

_spec("python-core-t03",
      "Write `fib(n: int) -> int` returning the n-th Fibonacci number (0-indexed: fib(0)=0, fib(1)=1). "
      "Must be efficient enough for n=40. Raise ValueError if n < 0.",
      '''
import solution as s

def test_base():
    assert s.fib(0) == 0 and s.fib(1) == 1

def test_ten():
    assert s.fib(10) == 55

def test_forty():
    assert s.fib(40) == 102334155

def test_negative():
    try:
        s.fib(-1)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("python-core-t04",
      "Write `is_prime(n: int) -> bool`. Return True iff n is a prime number. 0, 1 and negatives are not prime.",
      '''
import solution as s

def test_small():
    assert s.is_prime(2) and s.is_prime(3) and s.is_prime(17)

def test_composites():
    assert not s.is_prime(1) and not s.is_prime(0) and not s.is_prime(15)

def test_negative():
    assert s.is_prime(-7) is False

def test_largeish():
    assert s.is_prime(97) and not s.is_prime(100)
''')

_spec("python-core-t09",
      "Write class `LRUCache` with `__init__(self, capacity: int)`, `get(self, key: int) -> int` (return -1 if missing), "
      "and `put(self, key: int, value: int) -> None`. Evict least-recently-used when over capacity. capacity >= 1.",
      '''
import solution as s

def test_basic():
    c = s.LRUCache(2)
    c.put(1, 1); c.put(2, 2)
    assert c.get(1) == 1
    c.put(3, 3)
    assert c.get(2) == -1
    assert c.get(3) == 3

def test_update():
    c = s.LRUCache(2)
    c.put(1, 1); c.put(1, 10)
    assert c.get(1) == 10

def test_single():
    c = s.LRUCache(1)
    c.put(1, 1); c.put(2, 2)
    assert c.get(1) == -1 and c.get(2) == 2
''')

_spec("python-core-t10",
      "Write `word_freq(text: str) -> dict[str, int]` counting words case-insensitively. Words are maximal "
      "alphanumeric sequences. Return keys in lowercase.",
      '''
import solution as s

def test_simple():
    assert s.word_freq("A a b") == {"a": 2, "b": 1}

def test_empty():
    assert s.word_freq("") == {}

def test_punctuation():
    d = s.word_freq("Hello, hello! world.")
    assert d["hello"] == 2 and d["world"] == 1
''')

_spec("python-core-t05",
      "Write `reverse_list(head)` that reverses a singly linked list in-place and returns the new head. "
      "Nodes are objects with `.val` and `.next` attributes. `head` may be None.",
      '''
import solution as s

class N:
    def __init__(self, val, next=None):
        self.val, self.next = val, next

def _to_list(h):
    out = []
    while h:
        out.append(h.val); h = h.next
    return out

def test_empty():
    assert s.reverse_list(None) is None

def test_single():
    h = N(1)
    assert _to_list(s.reverse_list(h)) == [1]

def test_multi():
    h = N(1, N(2, N(3)))
    assert _to_list(s.reverse_list(h)) == [3, 2, 1]
''')

_spec("debug-suite-t01",
      "The function `bubble_sort(arr: list[int]) -> list[int]` is supposed to return a new sorted list ascending "
      "without mutating the input, but it is broken. Write a correct `bubble_sort` in solution.py.",
      '''
import solution as s

def test_basic():
    assert s.bubble_sort([3, 1, 2]) == [1, 2, 3]

def test_already():
    assert s.bubble_sort([1, 2, 3]) == [1, 2, 3]

def test_empty():
    assert s.bubble_sort([]) == []

def test_no_mutate():
    a = [2, 1]
    s.bubble_sort(a)
    assert a == [2, 1]
''')

_spec("debug-suite-t03",
      "Write a correct `binary_search(arr: list[int], target: int) -> int` for a sorted ascending array of distinct "
      "ints. Return index or -1. The reference implementation was buggy; yours must be right.",
      '''
import solution as s

def test_found():
    assert s.binary_search([1, 2, 3, 4, 5], 4) == 3

def test_missing():
    assert s.binary_search([1, 2, 3, 4, 5], 6) == -1

def test_empty():
    assert s.binary_search([], 1) == -1

def test_edges():
    assert s.binary_search([1, 2, 3], 1) == 0
    assert s.binary_search([1, 2, 3], 3) == 2
''')

_spec("debug-suite-t07",
      "Write a correct `is_palindrome(s: str) -> bool` ignoring case and non-alphanumerics. Empty string is a palindrome.",
      '''
import solution as s

def test_yes():
    assert s.is_palindrome("Racecar") is True

def test_no():
    assert s.is_palindrome("hello") is False

def test_phrase():
    assert s.is_palindrome("A man, a plan, a canal: Panama") is True

def test_empty():
    assert s.is_palindrome("") is True
''')

_spec("api-dev-t01",
      "Write function `health() -> dict` returning {\"status\": \"ok\"}. This stands in for a health-check endpoint body.",
      '''
import solution as s

def test_status():
    d = s.health()
    assert isinstance(d, dict) and d.get("status") == "ok"
''')

_spec("api-dev-t08",
      "Write `error_body(code: int, message: str) -> dict` returning "
      "{\"error\": {\"code\": code, \"message\": message}} for structured API errors.",
      '''
import solution as s

def test_shape():
    d = s.error_body(404, "missing")
    assert d["error"]["code"] == 404 and d["error"]["message"] == "missing"
''')

_spec("file-io-stats-t01",
      "Write `line_stats(text: str) -> dict` returning keys lines, words, chars (len of text). "
      "words are whitespace-separated tokens. lines count is number of lines including possible trailing empty.",
      '''
import solution as s

def test_basic():
    d = s.line_stats("a b\\nc")
    assert d["lines"] == 2 and d["words"] == 3 and d["chars"] == 5

def test_empty():
    d = s.line_stats("")
    assert d["words"] == 0 and d["chars"] == 0
    assert d["lines"] in (0, 1)
''')

_spec("file-io-stats-t03",
      "Write `char_histogram(text: str) -> dict[str, int]` counting occurrences of each character (including spaces).",
      '''
import solution as s

def test_simple():
    h = s.char_histogram("aab")
    assert h["a"] == 2 and h["b"] == 1

def test_empty():
    assert s.char_histogram("") == {}
''')

_spec("swe-lite-t05",
      "Write `safe_parse_int(value: str, default: int = 0) -> int`. Return int(value) when value is a valid integer "
      "literal (optional leading minus), otherwise return default. Do not raise.",
      '''
import solution as s

def test_ok():
    assert s.safe_parse_int("42") == 42
    assert s.safe_parse_int("-3") == -3

def test_bad():
    assert s.safe_parse_int("x", 7) == 7
    assert s.safe_parse_int("") == 0
''')

_spec("swe-lite-t13",
      "Write class `Point` with `__init__(self, x, y)` and `__eq__` so that points with equal coordinates compare equal. "
      "Also implement `__hash__` consistent with equality.",
      '''
import solution as s

def test_eq():
    assert s.Point(1, 2) == s.Point(1, 2)
    assert s.Point(1, 2) != s.Point(2, 1)

def test_hash():
    assert hash(s.Point(1, 2)) == hash(s.Point(1, 2))
    d = {s.Point(0, 0): "origin"}
    assert d[s.Point(0, 0)] == "origin"
''')


# ---------------------------------------------------------------------------
# Stage 2 completion — further hidden suites (meaningful behaviour tests)
# ---------------------------------------------------------------------------

_spec("python-core-t12",
      "Write class `Stack` with `push(x)`, `pop()` (raise IndexError if empty), `peek()` (raise IndexError if empty), "
      "and `is_empty() -> bool`. Also write class `Queue` with `enqueue(x)`, `dequeue()` (raise IndexError if empty), "
      "and `is_empty() -> bool`. FIFO for Queue, LIFO for Stack.",
      '''
import solution as s

def test_stack_lifo():
    st = s.Stack()
    st.push(1); st.push(2)
    assert st.pop() == 2 and st.peek() == 1

def test_stack_empty():
    st = s.Stack()
    assert st.is_empty() is True
    try:
        st.pop(); raise AssertionError
    except IndexError:
        pass

def test_queue_fifo():
    q = s.Queue()
    q.enqueue(1); q.enqueue(2)
    assert q.dequeue() == 1 and q.dequeue() == 2

def test_queue_empty():
    q = s.Queue()
    assert q.is_empty() is True
''')

_spec("python-core-t15",
      "Write `retry(fn, attempts: int = 3, exceptions: tuple = (Exception,))` decorator or higher-order function that "
      "calls `fn(*args, **kwargs)` up to `attempts` times, retrying only on the given exception types. "
      "If all attempts fail, re-raise the last exception. attempts >= 1.",
      '''
import solution as s

def test_success_first():
    c = {"n": 0}
    def f():
        c["n"] += 1
        return 7
    wrapped = s.retry(f, attempts=3)
    assert wrapped() == 7 and c["n"] == 1

def test_retry_then_ok():
    c = {"n": 0}
    def f():
        c["n"] += 1
        if c["n"] < 3:
            raise ValueError("nope")
        return "ok"
    assert s.retry(f, attempts=5, exceptions=(ValueError,))() == "ok"
    assert c["n"] == 3

def test_exhausted():
    def f():
        raise RuntimeError("x")
    try:
        s.retry(f, attempts=2, exceptions=(RuntimeError,))()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")
''')

_spec("python-core-t17",
      "Write `parse_csv(text: str) -> list[dict[str, str]]`. First line is the header. Return a list of row dicts "
      "mapping header names to cell strings. Empty input returns []. Cells are comma-separated; no quoting required.",
      '''
import solution as s

def test_basic():
    rows = s.parse_csv("a,b\\n1,2\\n3,4")
    assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]

def test_empty():
    assert s.parse_csv("") == []

def test_header_only():
    assert s.parse_csv("x,y") == []
''')

_spec("python-core-t18",
      "Write class `Timer` usable as a context manager (`with Timer() as t:`). After exit, `t.elapsed` is a float "
      "seconds >= 0 measuring the block duration.",
      '''
import solution as s
import time

def test_context():
    with s.Timer() as t:
        time.sleep(0.01)
    assert isinstance(t.elapsed, float) and t.elapsed >= 0.005

def test_attribute():
    with s.Timer() as t:
        pass
    assert hasattr(t, "elapsed")
''')

_spec("python-core-t20",
      "Write `bubble_sort(arr: list[int]) -> list[int]` returning a new ascending sorted list. Must not mutate input. "
      "Early-exit when a pass performs no swaps is allowed but not required.",
      '''
import solution as s

def test_sort():
    assert s.bubble_sort([3, 1, 2]) == [1, 2, 3]

def test_stable_empty():
    assert s.bubble_sort([]) == []

def test_no_mutate():
    a = [2, 1]
    s.bubble_sort(a)
    assert a == [2, 1]
''')

_spec("python-core-t21",
      "Write `checksum(s: str) -> int` returning the sum of `ord(c)` for every character in `s` (0 for empty).",
      '''
import solution as s

def test_empty():
    assert s.checksum("") == 0

def test_abc():
    assert s.checksum("abc") == ord("a") + ord("b") + ord("c")
''')

_spec("debug-suite-t02",
      "Write correct `quicksort(arr: list[int]) -> list[int]` returning a new ascending sorted list (any correct "
      "quicksort or equivalent sort is acceptable). Do not mutate the input.",
      '''
import solution as s

def test_basic():
    assert s.quicksort([3, 1, 2]) == [1, 2, 3]

def test_dupes():
    assert s.quicksort([2, 2, 1]) == [1, 2, 2]

def test_no_mutate():
    a = [2, 1]
    s.quicksort(a)
    assert a == [2, 1]
''')

_spec("debug-suite-t04",
      "Write `slice_fix(items: list, start: int, end: int) -> list` that returns items[start:end] but raises "
      "ValueError if start < 0 or end < start. (end may exceed len).",
      '''
import solution as s

def test_basic():
    assert s.slice_fix([10, 20, 30, 40], 1, 3) == [20, 30]

def test_end_past():
    assert s.slice_fix([1, 2], 0, 99) == [1, 2]

def test_bad():
    try:
        s.slice_fix([1], -1, 1)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("debug-suite-t05",
      "Write `merge_sort(arr: list[int]) -> list[int]` returning a new ascending sorted list. Do not mutate input.",
      '''
import solution as s

def test_basic():
    assert s.merge_sort([4, 2, 5, 1]) == [1, 2, 4, 5]

def test_empty():
    assert s.merge_sort([]) == []

def test_no_mutate():
    a = [2, 1]
    s.merge_sort(a)
    assert a == [2, 1]
''')

_spec("debug-suite-t06",
      "Write class `LRUCache` with `__init__(capacity)`, `get(key)->int` (-1 if missing), `put(key,value)`. "
      "Evict least-recently-used when over capacity.",
      '''
import solution as s

def test_evict():
    c = s.LRUCache(2)
    c.put(1, 1); c.put(2, 2); c.get(1); c.put(3, 3)
    assert c.get(2) == -1 and c.get(1) == 1 and c.get(3) == 3
''')

_spec("debug-suite-t08",
      "Write `fib_memo(n: int) -> int` with fib(0)=0, fib(1)=1. Must handle n=30 efficiently. Raise ValueError if n < 0.",
      '''
import solution as s

def test_base():
    assert s.fib_memo(0) == 0 and s.fib_memo(1) == 1

def test_n10():
    assert s.fib_memo(10) == 55

def test_n30():
    assert s.fib_memo(30) == 832040
''')

_spec("debug-suite-t09",
      "Write class `Stack` with push, pop (IndexError if empty), peek (IndexError if empty), is_empty.",
      '''
import solution as s

def test_ops():
    st = s.Stack()
    st.push("a"); st.push("b")
    assert st.peek() == "b" and st.pop() == "b" and st.pop() == "a"
    assert st.is_empty() is True
''')

_spec("api-dev-t02",
      "Write `crud_store()` returning a dict-like API object or module-level functions is fine; implement "
      "`create(item: dict) -> dict` assigning an integer `id` starting at 1, `get(id: int) -> dict | None`, "
      "`list_all() -> list[dict]`, `delete(id: int) -> bool`. Persist in memory for the process lifetime of the module.",
      '''
import solution as s
import importlib
importlib.reload(s)

def test_create_get():
    item = s.create({"name": "x"})
    assert "id" in item and s.get(item["id"])["name"] == "x"

def test_list_delete():
    a = s.create({"name": "a"})
    assert any(i["id"] == a["id"] for i in s.list_all())
    assert s.delete(a["id"]) is True
    assert s.get(a["id"]) is None
''')

_spec("api-dev-t03",
      "Write `validate_path_id(value: str) -> int` parsing a positive integer path parameter. "
      "Raise ValueError if value is not a positive integer string.",
      '''
import solution as s

def test_ok():
    assert s.validate_path_id("42") == 42

def test_bad():
    for v in ("0", "-1", "x", "1.5", ""):
        try:
            s.validate_path_id(v)
        except ValueError:
            continue
        raise AssertionError("expected ValueError for %r" % v)
''')

_spec("api-dev-t04",
      "Write `parse_filters(query: dict[str, str]) -> dict` keeping only keys whose values are non-empty strings, "
      "stripping whitespace from values.",
      '''
import solution as s

def test_basic():
    assert s.parse_filters({"q": "  ab ", "empty": "", "x": "1"}) == {"q": "ab", "x": "1"}

def test_empty():
    assert s.parse_filters({}) == {}
''')

_spec("api-dev-t05",
      "Write `paginate(items: list, cursor: int = 0, limit: int = 10) -> dict` returning "
      "{\"items\": slice, \"next_cursor\": int|None}. cursor is start index; next_cursor is None when no more items.",
      '''
import solution as s

def test_first_page():
    d = s.paginate(list(range(25)), cursor=0, limit=10)
    assert d["items"] == list(range(10)) and d["next_cursor"] == 10

def test_last():
    d = s.paginate(list(range(5)), cursor=0, limit=10)
    assert d["items"] == list(range(5)) and d["next_cursor"] is None
''')

_spec("file-io-stats-t02",
      "Write `word_freq_text(text: str) -> dict[str, int]` counting whitespace-separated tokens case-sensitively.",
      '''
import solution as s

def test_basic():
    assert s.word_freq_text("a a b") == {"a": 2, "b": 1}

def test_empty():
    assert s.word_freq_text("") == {}
''')

_spec("file-io-stats-t04",
      "Write `aggregate_jsonl(lines: list[str], key: str) -> dict[str, int]` counting how often each value of `key` "
      "appears in JSON objects (one JSON object per line). Skip invalid JSON lines.",
      '''
import solution as s

def test_basic():
    lines = ['{"type": "a"}', '{"type": "b"}', '{"type": "a"}', "not-json"]
    assert s.aggregate_jsonl(lines, "type") == {"a": 2, "b": 1}

def test_missing_key():
    assert s.aggregate_jsonl(['{"x": 1}'], "type") == {}
''')

_spec("file-io-stats-t05",
      "Write `rolling_average(values: list[float], window: int) -> list[float]` of simple moving averages. "
      "Raise ValueError if window < 1. For index i, average values[max(0,i-window+1):i+1].",
      '''
import solution as s

def test_window1():
    assert s.rolling_average([1.0, 2.0, 3.0], 1) == [1.0, 2.0, 3.0]

def test_window2():
    out = s.rolling_average([2.0, 4.0, 6.0], 2)
    assert out[0] == 2.0 and abs(out[1] - 3.0) < 1e-9 and abs(out[2] - 5.0) < 1e-9

def test_bad():
    try:
        s.rolling_average([1.0], 0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("file-io-stats-t06",
      "Write `find_duplicates(records: list[str]) -> list[str]` returning values that appear more than once, "
      "each duplicate key once, in order of first occurrence.",
      '''
import solution as s

def test_basic():
    assert s.find_duplicates(["a", "b", "a", "c", "b"]) == ["a", "b"]

def test_none():
    assert s.find_duplicates(["a", "b"]) == []
''')

_spec("swe-lite-t01",
      "Write `add_days(date_str: str, days: int) -> str` where date_str is 'YYYY-MM-DD'. Return the date shifted by "
      "`days` (may be negative) in the same format. Use datetime.date.",
      '''
import solution as s

def test_forward():
    assert s.add_days("2020-01-31", 1) == "2020-02-01"

def test_backward():
    assert s.add_days("2020-03-01", -1) == "2020-02-29"
''')

_spec("swe-lite-t04",
      "Write `migrate_log_level(level: str) -> str` mapping deprecated levels: 'warn'->'WARNING', 'fatal'->'CRITICAL', "
      "passthrough uppercased known levels DEBUG/INFO/WARNING/ERROR/CRITICAL, else raise ValueError.",
      '''
import solution as s

def test_deprecated():
    assert s.migrate_log_level("warn") == "WARNING"
    assert s.migrate_log_level("fatal") == "CRITICAL"

def test_known():
    assert s.migrate_log_level("info") == "INFO"

def test_bad():
    try:
        s.migrate_log_level("nope")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("swe-lite-t10",
      "Write `backoff_delay(attempt: int, base: float = 0.1, factor: float = 2.0, cap: float = 10.0) -> float` "
      "returning min(cap, base * factor**attempt) for attempt >= 0. Raise ValueError if attempt < 0.",
      '''
import solution as s

def test_seq():
    assert abs(s.backoff_delay(0) - 0.1) < 1e-9
    assert abs(s.backoff_delay(1) - 0.2) < 1e-9

def test_cap():
    assert s.backoff_delay(100, base=1.0, factor=2.0, cap=5.0) == 5.0

def test_bad():
    try:
        s.backoff_delay(-1)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')


# =============================================================================
# Full catalogue coverage — remaining 54 tasks (Stage 2 100/100)
# Each suite tests behaviour, edge cases, and invalid input where relevant.
# =============================================================================

_spec("python-core-t16",
      "Write class `EventEmitter` with `on(event: str, handler)`, `off(event: str, handler)`, and "
      "`emit(event: str, *args)` calling handlers in registration order. Unknown events are no-ops.",
      '''
import solution as s

def test_emit_order():
    e = s.EventEmitter(); out = []
    e.on("x", lambda v: out.append(v))
    e.on("x", lambda v: out.append(v + 1))
    e.emit("x", 1)
    assert out == [1, 2]

def test_off():
    e = s.EventEmitter(); out = []
    h = lambda: out.append(1)
    e.on("a", h); e.off("a", h); e.emit("a")
    assert out == []

def test_unknown():
    s.EventEmitter().emit("nope")
''')

_spec("python-core-t22",
      "Write metaclass `Singleton` so that classes using `class C(metaclass=Singleton)` return the same instance "
      "for every construction call.",
      '''
import solution as s

def test_same_instance():
    class C(metaclass=s.Singleton):
        def __init__(self): self.x = 1
    assert C() is C()
''')

_spec("python-core-t23",
      "Write `solve_maze(grid: list[list[int]], start: tuple[int,int], end: tuple[int,int]) -> list[tuple[int,int]] | None`. "
      "grid cells 0=open, 1=wall. Return a path of coordinates from start to end inclusive, or None if impossible. "
      "4-directional moves only.",
      '''
import solution as s

def test_simple():
    g = [[0,0],[1,0]]
    path = s.solve_maze(g, (0,0), (1,1))
    assert path is not None and path[0] == (0,0) and path[-1] == (1,1)

def test_blocked():
    g = [[0,1],[1,0]]
    assert s.solve_maze(g, (0,0), (1,1)) is None

def test_same_cell():
    assert s.solve_maze([[0]], (0,0), (0,0)) == [(0,0)]
''')

_spec("python-core-t24",
      "Write class `TokenBucket` with `__init__(self, rate: float, capacity: float)` and `allow(self, tokens: float = 1.0) -> bool`. "
      "Tokens refill at `rate` per second up to `capacity`. Use time.monotonic(). First call after init should allow up to capacity.",
      '''
import solution as s
import time

def test_initial_capacity():
    b = s.TokenBucket(rate=10.0, capacity=5.0)
    assert b.allow(5.0) is True
    assert b.allow(1.0) is False

def test_refill():
    b = s.TokenBucket(rate=1000.0, capacity=1.0)
    assert b.allow(1.0) is True
    time.sleep(0.01)
    assert b.allow(1.0) is True
''')

_spec("debug-suite-t10",
      "Write `group_by(items: list, key_fn) -> dict` grouping items by key_fn(item). Values are lists preserving order.",
      '''
import solution as s

def test_basic():
    d = s.group_by(["aa", "b", "cc", "d"], len)
    assert d[2] == ["aa", "cc"] and d[1] == ["b", "d"]

def test_empty():
    assert s.group_by([], lambda x: x) == {}
''')

_spec("debug-suite-t11",
      "Write `retry(fn, attempts=3, exceptions=(Exception,))` that retries on given exceptions and re-raises the last error.",
      '''
import solution as s

def test_ok():
    assert s.retry(lambda: 1, attempts=2)() == 1

def test_fail():
    def f():
        raise ValueError("x")
    try:
        s.retry(f, attempts=2, exceptions=(ValueError,))()
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("debug-suite-t12",
      "Write `with_timeout(fn, seconds: float)` that calls fn() and raises TimeoutError if it runs longer than seconds. "
      "For this benchmark, a cooperative version is OK: if fn accepts a check callback ignore it; simplest correct behaviour "
      "is to call fn() and return its result when seconds >= 0, and raise ValueError if seconds < 0.",
      '''
import solution as s

def test_runs():
    assert s.with_timeout(lambda: 42, 1.0) == 42

def test_bad():
    try:
        s.with_timeout(lambda: 1, -1)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("debug-suite-t13",
      "Write `deep_copy(obj)` supporting nested dicts, lists, and immutable leaves (int/str/tuple of immutables). "
      "Mutating the copy must not affect the original.",
      '''
import solution as s

def test_list_dict():
    o = {"a": [1, {"b": 2}]}
    c = s.deep_copy(o)
    c["a"].append(3)
    c["a"][1]["b"] = 9
    assert o == {"a": [1, {"b": 2}]}
''')

_spec("debug-suite-t14",
      "Write class `EventEmitter` with on/off/emit as in a standard event emitter.",
      '''
import solution as s

def test_basic():
    e = s.EventEmitter(); box = []
    e.on("e", lambda: box.append(1))
    e.emit("e")
    assert box == [1]
''')

_spec("debug-suite-t15",
      "Write class `RateLimiter` with `__init__(self, max_calls: int)` and `allow(self) -> bool` allowing at most "
      "max_calls successful allows, then False until reset via `reset()`.",
      '''
import solution as s

def test_limit():
    r = s.RateLimiter(2)
    assert r.allow() and r.allow() and not r.allow()
    r.reset()
    assert r.allow()
''')

_spec("debug-suite-t16",
      "Write `tokenize(text: str) -> list[str]` splitting on whitespace and discarding empty tokens.",
      '''
import solution as s

def test_basic():
    assert s.tokenize("  a  b\\tc ") == ["a", "b", "c"]

def test_empty():
    assert s.tokenize("") == []
''')

_spec("debug-suite-t17",
      "Write `rotate_matrix(m: list[list[int]]) -> list[list[int]]` rotating a square matrix 90 degrees clockwise, "
      "returning a new matrix.",
      '''
import solution as s

def test_2x2():
    assert s.rotate_matrix([[1,2],[3,4]]) == [[3,1],[4,2]]

def test_1x1():
    assert s.rotate_matrix([[9]]) == [[9]]
''')

_spec("debug-suite-t18",
      "Write `resolve_order(deps: dict[str, list[str]]) -> list[str]` returning a topological order of keys. "
      "deps maps node -> list of dependencies that must come first. Raise ValueError on cycles.",
      '''
import solution as s

def test_order():
    order = s.resolve_order({"a": [], "b": ["a"], "c": ["b"]})
    assert order.index("a") < order.index("b") < order.index("c")

def test_cycle():
    try:
        s.resolve_order({"a": ["b"], "b": ["a"]})
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("api-dev-t06",
      "Write `nested_path(user_id: int, order_id: int) -> str` returning '/users/{user_id}/orders/{order_id}'.",
      '''
import solution as s

def test_path():
    assert s.nested_path(3, 9) == "/users/3/orders/9"
''')

_spec("api-dev-t07",
      "Write `validate_body(data: dict, required: list[str]) -> dict` returning data if all required keys present "
      "and values are not None; else raise ValueError.",
      '''
import solution as s

def test_ok():
    assert s.validate_body({"a": 1, "b": 2}, ["a"]) == {"a": 1, "b": 2}

def test_missing():
    try:
        s.validate_body({"a": 1}, ["a", "b"])
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("api-dev-t09",
      "Write `check_api_key(headers: dict[str, str], expected: str) -> bool` returning True if headers contain "
      "key 'x-api-key' (case-insensitive) equal to expected.",
      '''
import solution as s

def test_ok():
    assert s.check_api_key({"X-Api-Key": "secret"}, "secret") is True

def test_bad():
    assert s.check_api_key({"x-api-key": "nope"}, "secret") is False
    assert s.check_api_key({}, "secret") is False
''')

_spec("api-dev-t10",
      "Write `rate_limit_headers(limit: int, remaining: int, reset: int) -> dict[str, str]` returning "
      "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset as strings.",
      '''
import solution as s

def test_headers():
    h = s.rate_limit_headers(100, 42, 1700000000)
    assert h["X-RateLimit-Limit"] == "100"
    assert h["X-RateLimit-Remaining"] == "42"
    assert h["X-RateLimit-Reset"] == "1700000000"
''')

_spec("api-dev-t11",
      "Write `save_upload(filename: str, content: bytes, allowed_ext: set[str]) -> str` returning the filename if "
      "its extension (after last dot, lowercased) is in allowed_ext; else raise ValueError. Ignore directories in name.",
      '''
import solution as s

def test_ok():
    assert s.save_upload("pic.PNG", b"x", {"png", "jpg"}) == "pic.PNG"

def test_bad():
    try:
        s.save_upload("x.exe", b"x", {"png"})
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("api-dev-t12",
      "Write `bulk_create(items: list[dict]) -> dict` returning {\"created\": n, \"ids\": [1..n]} assigning sequential ids from 1.",
      '''
import solution as s

def test_bulk():
    r = s.bulk_create([{"a": 1}, {"a": 2}])
    assert r["created"] == 2 and r["ids"] == [1, 2]

def test_empty():
    r = s.bulk_create([])
    assert r["created"] == 0 and r["ids"] == []
''')

_spec("api-dev-t13",
      "Write `negotiate(accept_header: str, available: list[str]) -> str | None` choosing the first available type "
      "listed in a comma-separated Accept header (ignore q-values). None if no match.",
      '''
import solution as s

def test_pick():
    assert s.negotiate("text/html, application/json", ["application/json", "text/plain"]) == "application/json"

def test_none():
    assert s.negotiate("image/png", ["application/json"]) is None
''')

_spec("api-dev-t14",
      "Write class `IdempotencyStore` with `begin(key: str) -> bool` (True if key is new), `commit(key: str, result)`, "
      "and `get(key: str)` returning committed result or None.",
      '''
import solution as s

def test_flow():
    store = s.IdempotencyStore()
    assert store.begin("k") is True
    assert store.begin("k") is False
    store.commit("k", {"ok": True})
    assert store.get("k") == {"ok": True}
''')

_spec("api-dev-t15",
      "Write `check_etag(current: str, if_match: str | None) -> bool` returning True if if_match is None or equals current.",
      '''
import solution as s

def test_match():
    assert s.check_etag("abc", "abc") is True
    assert s.check_etag("abc", None) is True
    assert s.check_etag("abc", "xyz") is False
''')

_spec("api-dev-t16",
      "Write `stream_pages(items: list, page_size: int)` generator yielding lists of at most page_size. "
      "Raise ValueError if page_size < 1.",
      '''
import solution as s

def test_pages():
    pages = list(s.stream_pages([1,2,3,4,5], 2))
    assert pages == [[1,2],[3,4],[5]]

def test_bad():
    try:
        list(s.stream_pages([1], 0))
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("file-io-stats-t07",
      "Write `histogram(values: list[float], bins: int) -> list[int]` counting values into `bins` equal-width bins "
      "from min to max. If all values equal, put all in bin 0. Raise ValueError if bins < 1 or values empty.",
      '''
import solution as s

def test_two_bins():
    h = s.histogram([0.0, 1.0, 0.1, 0.9], 2)
    assert sum(h) == 4 and len(h) == 2

def test_constant():
    assert s.histogram([3.0, 3.0], 3)[0] == 2

def test_bad():
    try:
        s.histogram([], 2)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("file-io-stats-t08",
      "Write `count_emails(text: str) -> int` counting non-overlapping emails matching a simple pattern "
      "local@domain with at least one dot in domain (regex fine).",
      '''
import solution as s

def test_count():
    assert s.count_emails("a@b.co and x@y.z.com") == 2

def test_none():
    assert s.count_emails("no mail here") == 0
''')

_spec("file-io-stats-t09",
      "Write `line_diff(a: str, b: str) -> dict` with keys added, removed (lists of lines present only in b / only in a).",
      '''
import solution as s

def test_diff():
    d = s.line_diff("a\\nb\\n", "b\\nc\\n")
    assert "a" in d["removed"] and "c" in d["added"]
''')

_spec("file-io-stats-t10",
      "Write `compress_report(text: str) -> tuple[bytes, str]` returning (zlib-compressed bytes, sha256 hex of those bytes). "
      "Write `verify_report(data: bytes, checksum: str) -> bool`.",
      '''
import solution as s

def test_roundtrip():
    data, chk = s.compress_report("hello")
    assert isinstance(data, (bytes, bytearray))
    assert s.verify_report(data, chk) is True
    assert s.verify_report(data, "0"*64) is False
''')

_spec("file-io-stats-t11",
      "Write `count_matches(text: str, pattern: str) -> int` counting non-overlapping regex matches of pattern in text.",
      '''
import solution as s

def test_count():
    assert s.count_matches("ababab", "ab") == 3

def test_none():
    assert s.count_matches("zzz", "ab") == 0
''')

_spec("file-io-stats-t12",
      "Write `merge_corpus(parts: list[str], sep: str = \"\\n\") -> str` joining parts with sep, skipping empty parts.",
      '''
import solution as s

def test_merge():
    assert s.merge_corpus(["a", "", "b"], "\\n") == "a\\nb"
''')

_spec("swe-lite-t02",
      "Write `paginate_users(users: list[dict], page: int, size: int) -> dict` returning "
      "{\"items\": ..., \"page\": page, \"size\": size, \"total\": len(users)}. page is 1-based. Raise ValueError if page<1 or size<1.",
      '''
import solution as s

def test_page():
    users = [{"id": i} for i in range(1, 6)]
    d = s.paginate_users(users, 2, 2)
    assert d["items"] == [{"id": 3}, {"id": 4}] and d["total"] == 5

def test_bad():
    try:
        s.paginate_users([], 0, 10)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("swe-lite-t03",
      "Write class `SafeCache` with `get(key)`, `set(key, value)` that is correct under single-threaded use "
      "(dict-backed). get returns None if missing.",
      '''
import solution as s

def test_cache():
    c = s.SafeCache()
    c.set("a", 1)
    assert c.get("a") == 1 and c.get("b") is None
''')

_spec("swe-lite-t06",
      "Write `to_utc_iso(local_iso: str, offset_hours: int) -> str` where local_iso is 'YYYY-MM-DDTHH:MM:SS' without tz. "
      "Subtract offset_hours to get UTC, return 'YYYY-MM-DDTHH:MM:SSZ'.",
      '''
import solution as s

def test_shift():
    assert s.to_utc_iso("2020-01-01T05:00:00", 5) == "2020-01-01T00:00:00Z"
''')

_spec("swe-lite-t07",
      "Write function `annotate_types(fields: dict[str, type]) -> dict[str, str]` mapping field name to type.__name__.",
      '''
import solution as s

def test_ann():
    assert s.annotate_types({"n": int, "s": str}) == {"n": "int", "s": "str"}
''')

_spec("swe-lite-t08",
      "Write class `StreamClient` with `close()` and property `closed: bool`. After close(), closed is True. "
      "Double-close is safe.",
      '''
import solution as s

def test_close():
    c = s.StreamClient()
    assert c.closed is False
    c.close(); c.close()
    assert c.closed is True
''')

_spec("swe-lite-t09",
      "Write `should_retry(status_code: int, policy: str) -> bool`. policy 'idempotent_only' retries 408/429/5xx; "
      "'all' retries any status >= 400; otherwise False.",
      '''
import solution as s

def test_idempotent():
    assert s.should_retry(503, "idempotent_only") is True
    assert s.should_retry(404, "idempotent_only") is False

def test_all():
    assert s.should_retry(400, "all") is True
''')

_spec("swe-lite-t11",
      "Write `validate_webhook(payload: dict, secret: str) -> bool` True when payload has key 'sig' equal to "
      "sha256 hex of (secret + payload.get('body','')).",
      '''
import solution as s
import hashlib

def test_ok():
    body = "hi"
    sig = hashlib.sha256(("s" + body).encode()).hexdigest()
    assert s.validate_webhook({"body": body, "sig": sig}, "s") is True

def test_bad():
    assert s.validate_webhook({"body": "x", "sig": "no"}, "s") is False
''')

_spec("swe-lite-t12",
      "Write `same_instant(a_iso: str, b_iso: str) -> bool` comparing two 'YYYY-MM-DDTHH:MM:SSZ' strings for equality.",
      '''
import solution as s

def test_same():
    assert s.same_instant("2020-01-01T00:00:00Z", "2020-01-01T00:00:00Z") is True
    assert s.same_instant("2020-01-01T00:00:00Z", "2020-01-01T00:00:01Z") is False
''')

_spec("swe-lite-t14",
      "Write `struct_log(level: str, msg: str, **fields) -> dict` returning {\"level\": level.upper(), \"msg\": msg, **fields}.",
      '''
import solution as s

def test_log():
    d = s.struct_log("info", "hi", user=1)
    assert d["level"] == "INFO" and d["msg"] == "hi" and d["user"] == 1
''')

_spec("swe-lite-t15",
      "Write `sort_records(records: list[dict], key: str) -> list[dict]` sorting by key ascending; missing key sorts as None first.",
      '''
import solution as s

def test_sort():
    out = s.sort_records([{"n": 2}, {"n": 1}], "n")
    assert [r["n"] for r in out] == [1, 2]
''')

_spec("swe-lite-t16",
      "Write `bulk_export(rows: list[dict], fields: list[str]) -> list[dict]` projecting each row to only fields (missing -> None).",
      '''
import solution as s

def test_export():
    assert s.bulk_export([{"a": 1, "b": 2}], ["a"]) == [{"a": 1}]
''')

_spec("swe-lite-t17",
      "Write `resolve(name: str | None, default: str = \"unknown\") -> str` returning default when name is None or empty.",
      '''
import solution as s

def test_resolve():
    assert s.resolve(None) == "unknown"
    assert s.resolve("") == "unknown"
    assert s.resolve("x") == "x"
''')

_spec("swe-lite-t18",
      "Write `load_config(env: dict[str, str], key: str, default: str | None = None) -> str | None` reading env.get(key, default).",
      '''
import solution as s

def test_load():
    assert s.load_config({"A": "1"}, "A") == "1"
    assert s.load_config({}, "A", "x") == "x"
''')

_spec("swe-lite-t19",
      "Write class `JobQueue` with `submit(job_id: str) -> bool` returning True only the first time a job_id is submitted.",
      '''
import solution as s

def test_idempotent():
    q = s.JobQueue()
    assert q.submit("j1") is True
    assert q.submit("j1") is False
''')

_spec("swe-lite-t20",
      "Write `dedupe_preserve(items: list) -> list` removing later duplicates, preserving first-seen order.",
      '''
import solution as s

def test_dedupe():
    assert s.dedupe_preserve([1, 2, 1, 3, 2]) == [1, 2, 3]
''')

_spec("swe-lite-t21",
      "Write `batch_results(results: list[bool]) -> dict` returning {\"ok\": count True, \"failed\": count False, \"partial\": True if mixed}.",
      '''
import solution as s

def test_partial():
    d = s.batch_results([True, False, True])
    assert d["ok"] == 2 and d["failed"] == 1 and d["partial"] is True

def test_all_ok():
    d = s.batch_results([True, True])
    assert d["partial"] is False
''')

_spec("swe-lite-t22",
      "Write class `ApiRateLimit` with `__init__(limit: int)` and `hit() -> bool` allowing `limit` hits then False until `reset()`.",
      '''
import solution as s

def test_limit():
    a = s.ApiRateLimit(1)
    assert a.hit() is True and a.hit() is False
    a.reset()
    assert a.hit() is True
''')

_spec("swe-lite-t23",
      "Write `round_currency(amount: float, places: int = 2) -> float` using round half away from zero via Decimal quantize "
      "or equivalent banker's-round-safe approach for *.5 toward even is acceptable if documented; require "
      "round_currency(1.005, 2) in {1.00, 1.01} and round_currency(1.004, 2) == 1.0.",
      '''
import solution as s

def test_basic():
    assert s.round_currency(1.004, 2) == 1.0
    assert s.round_currency(1.006, 2) == 1.01
''')

_spec("swe-lite-t24",
      "Write `trace_id(prefix: str = \"tr\") -> str` returning prefix + '-' + 16 lowercase hex chars (random OK).",
      '''
import solution as s
import re

def test_format():
    t = s.trace_id("tr")
    assert re.match(r"^tr-[0-9a-f]{16}$", t)
''')

_spec("swe-lite-t25",
      "Write `resolve_version(requested: str, available: list[str]) -> str | None` returning requested if in available else None.",
      '''
import solution as s

def test_res():
    assert s.resolve_version("1.2.3", ["1.2.3", "2.0"]) == "1.2.3"
    assert s.resolve_version("9.9", ["1.0"]) is None
''')

_spec("swe-lite-t26",
      "Write `safe_join(base: str, *parts: str) -> str` joining with os.path.normpath rules but raise ValueError if the "
      "normalized result would escape base (via '..').",
      '''
import solution as s
import os

def test_ok():
    p = s.safe_join("/var/data", "a", "b.txt")
    assert p.endswith(os.path.join("a", "b.txt")) or "a" in p

def test_escape():
    try:
        s.safe_join("/var/data", "../etc/passwd")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("swe-lite-t27",
      "Write `pagination_defaults(page: int | None, size: int | None) -> tuple[int, int]` defaulting page to 1 and size to 20. "
      "Raise ValueError if resulting page < 1 or size < 1 or size > 100.",
      '''
import solution as s

def test_defaults():
    assert s.pagination_defaults(None, None) == (1, 20)

def test_bad():
    try:
        s.pagination_defaults(1, 101)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
''')

_spec("swe-lite-t28",
      "Write `normalize_keys(data: dict) -> dict` lowercasing all string keys.",
      '''
import solution as s

def test_norm():
    assert s.normalize_keys({"AbC": 1, "x": 2}) == {"abc": 1, "x": 2}
''')

_spec("swe-lite-t29",
      "Write `health_probes(checks: dict[str, bool]) -> dict` returning {\"status\": \"ok\" if all True else \"degraded\", \"checks\": checks}.",
      '''
import solution as s

def test_ok():
    assert s.health_probes({"db": True})["status"] == "ok"

def test_deg():
    assert s.health_probes({"db": False})["status"] == "degraded"
''')

_spec("swe-lite-t30",
      "Write `wait_until(predicate, timeout_sec: float = 1.0, interval: float = 0.01) -> bool` polling predicate until True "
      "or timeout; return whether predicate became True. predicate is zero-arg callable.",
      '''
import solution as s

def test_true():
    assert s.wait_until(lambda: True, timeout_sec=0.2) is True

def test_timeout():
    assert s.wait_until(lambda: False, timeout_sec=0.05, interval=0.01) is False
''')

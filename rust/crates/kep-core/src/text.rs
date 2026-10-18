//! Text helpers from `core.py`.

use crate::pyval::py_isspace;
use unicode_normalization::UnicodeNormalization;
use unicode_normalization::char::canonical_combining_class;

/// `fold()`: Turkish-aware case and accent folding used for city matching.
///
/// ```python
/// text = text.replace('İ','I').replace('ı','i').lower()
/// ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c))
/// ```
pub fn fold(text: &str) -> String {
    let lowered = text.replace('İ', "I").replace('ı', "i").to_lowercase();
    lowered
        .nfd()
        .filter(|c| canonical_combining_class(*c) == 0)
        .collect()
}

/// `' '.join(text.split())`: collapse whitespace runs, trim the ends.
pub fn collapse_whitespace(text: &str) -> String {
    text.split(py_isspace)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

/// `text.strip()` with Python's whitespace set.
pub fn py_strip(text: &str) -> &str {
    text.trim_matches(py_isspace)
}

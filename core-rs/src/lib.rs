// Copyright (C) 2026 Vicente José Leiva Escárate
// SPDX-License-Identifier: GPL-3.0-or-later

//! Dependency-free native primitives shared by current and future Sylith apps.

#[no_mangle]
pub extern "C" fn meteo_validate_coordinates(latitude: f64, longitude: f64) -> i32 {
    (latitude.is_finite()
        && longitude.is_finite()
        && (-90.0..=90.0).contains(&latitude)
        && (-180.0..=180.0).contains(&longitude)) as i32
}

#[no_mangle]
pub unsafe extern "C" fn meteo_weighted_mean(
    values: *const f64,
    weights: *const f64,
    length: usize,
) -> f64 {
    if values.is_null() || weights.is_null() || length == 0 {
        return f64::NAN;
    }

    let values = std::slice::from_raw_parts(values, length);
    let weights = std::slice::from_raw_parts(weights, length);
    let mut weighted_sum = 0.0;
    let mut total_weight = 0.0;

    for (value, weight) in values.iter().zip(weights.iter()) {
        if value.is_finite() && weight.is_finite() && *weight > 0.0 {
            weighted_sum += value * weight;
            total_weight += weight;
        }
    }

    if total_weight == 0.0 {
        f64::NAN
    } else {
        weighted_sum / total_weight
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_coordinate_bounds() {
        assert_eq!(meteo_validate_coordinates(-39.28, -72.23), 1);
        assert_eq!(meteo_validate_coordinates(91.0, 0.0), 0);
    }

    #[test]
    fn calculates_weighted_mean() {
        let values = [10.0, 14.0];
        let weights = [1.0, 3.0];
        let result = unsafe {
            meteo_weighted_mean(values.as_ptr(), weights.as_ptr(), values.len())
        };
        assert!((result - 13.0).abs() < f64::EPSILON);
    }
}

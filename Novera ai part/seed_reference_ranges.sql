INSERT INTO reference_ranges (organ, biomarker, min_value, max_value, weight) VALUES
('KIDNEY',  'ph',                     6.2,  7.6, 1.0),
('KIDNEY',  'urea_mg_dl',            20.0, 30.0, 1.0),
('KIDNEY',  'creatinine_umol_l',     18.0, 25.0, 1.0),
('KIDNEY',  'temperature_c',         35.0, 37.0, 0.6),
('STOMACH', 'ph',                     6.5,  7.6, 1.0),
('STOMACH', 'urea_mg_dl',            20.0, 45.0, 1.0),
('STOMACH', 'creatinine_umol_l',     18.0, 40.0, 1.0),
('STOMACH', 'temperature_c',         35.0, 37.0, 0.6),
('ORAL',    'ph',                     6.3,  7.6, 1.0),
('ORAL',    'urea_mg_dl',            20.0, 45.0, 1.0),
('ORAL',    'creatinine_umol_l',     18.0, 40.0, 1.0),
('ORAL',    'temperature_c',         35.0, 37.0, 0.6)
ON CONFLICT (organ, biomarker) DO UPDATE SET
    min_value = excluded.min_value,
    max_value = excluded.max_value,
    weight = excluded.weight;

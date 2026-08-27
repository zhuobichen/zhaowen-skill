---
name: ylx_process_daily_pm25
description: This skill should be used when converting hourly PM2.5 station monitoring data to daily average concentrations. Use this for processing site-based hourly PM2.5 CSV files, calculating daily averages with quality control (>=20 valid hours), and generating daily and hourly PM2.5 monitoring data files with station coordinates.
license: MIT
---

# Process Daily PM2.5 Monitoring Data

This skill provides specialized tools for converting hourly PM2.5 station monitoring data to daily average concentrations with quality control. It can also output hourly-level data.

## Purpose

Convert hourly PM2.5 station monitoring data to daily average concentrations, applying quality control to ensure data reliability (>=20 valid hours per day). The skill processes TAP station data and outputs daily monitoring files with geographic coordinates. Optionally, it can also output hourly-level data files.

## When to Use This Skill

Use this skill when:
- Converting hourly PM2.5 monitoring data to daily averages
- Processing station-based hourly CSV files for air quality analysis
- Generating daily PM2.5 monitoring datasets with quality control
- Generating hourly PM2.5 monitoring datasets
- Adding station geographic coordinates (latitude/longitude) to monitoring data
- Processing annual monitoring data (e.g., 2014-2023)

## Workflow

### Step 1: Prepare Input Data

Ensure input data follows the required structure:

**Input data structure:**
- File naming: `china_sites_YYYYMMDD.csv` (e.g., `china_sites_20230101.csv`)
- Required columns: `date`, `hour`, `type`, [station columns]
- Station data format: Station IDs as column headers (e.g., `1001A`, `1002A`)
- Data type: `type` column should contain "PM2.5" for PM2.5 hourly measurements
- Hourly data: `hour` column ranges from 0-23

**Data folder:**
- Place yearly data in: `站点_YYYY0101-YYYY1231/站点_YYYY0101-YYYY12331/`
- Example: `站点_20230101-20231231/站点_20230101-20231231/`

### Step 2: Process Data

Execute the processing script to generate daily averages:

```bash
# Process a specific year (daily data only)
cd process-daily-pm25/scripts
python process_daily_pm25.py 2023

# Process a specific year (daily + hourly data)
python process_daily_pm25.py 2023 --hourly

# Process multiple years (daily + hourly data)
python process_daily_pm25.py 2023 2022 2021 --hourly

# Process from the working directory
python process_daily_pm25.py 2023 --workdir /path/to/working/directory --hourly
```

**Command arguments:**
- `year`: Target year to process (required)
- Additional years can be specified to process multiple years
- `--workdir`: Working directory (default: current directory)
- `--hourly`: Also output hourly-level data file

### Step 3: Review Results

Check output files and statistics:

**Output location:** `{workdir}/`

**Daily output file:**
- File naming: `{year}_DailyPM2.5Monitor.csv`
- Example: `2023_DailyPM2.5Monitor.csv`

**Hourly output file (when `--hourly` is specified):**
- File naming: `{year}_HourlyPM2.5Monitor.csv`
- Example: `2023_HourlyPM2.5Monitor.csv`

**Daily output format:**
- **Site**: Station ID
- **Date**: Date in YYYY-MM-DD format
- **Conc**: Daily average PM2.5 concentration (μg/m³)
- **Valid_Hours**: Number of valid hours (>=20 required for quality control)
- **Actual_Hour_Count**: Actual hourly records available for that day
- **Lat**: Latitude of the station
- **Lon**: Longitude of the station

**Hourly output format (when `--hourly` is specified):**
- **Site**: Station ID
- **Date**: Date and hour in YYYY-MM-DD HH format
- **Conc**: Hourly PM2.5 concentration (μg/m³)
- **Lat**: Latitude of the station
- **Lon**: Longitude of the station

**Quality Control Criteria:**
- Only days with >=20 valid hours are included in daily averages (83.3% of 24 hours)
- Station geographic coordinates are merged from `MonitorLatLonTable.csv`
- Stations without valid data are excluded from daily averages
- Hourly data includes all valid hourly measurements

## Processing Method

The skill uses hourly data aggregation with quality control:

**Daily Data Processing:**
1. Filter PM2.5 hourly data from input files
2. Count valid hours for each station (non-null values)
3. Apply quality control: only include stations with >=20 valid hours
4. Calculate daily average for qualified stations
5. Merge station geographic coordinates from `MonitorLatLonTable.csv`
6. Reshape data from wide to long format for analysis

**Hourly Data Processing (when `--hourly` is specified):**
1. Filter PM2.5 hourly data from input files
2. Reshape from wide to long format
3. Filter out null values
4. Merge station geographic coordinates from `MonitorLatLonTable.csv`
5. Format date-time as YYYY-MM-DD HH

**Quality Control Standards:**
- Minimum valid hours: 20 hours per day (83.3% of 24 hours) for daily averages
- Stations failing quality control are excluded from daily calculations
- Daily statistics report valid stations vs. total stations
- Hourly data includes all valid hourly measurements

## Dependencies

Required Python packages:
- pandas
- numpy

**Installation:**
```bash
pip install pandas numpy
```

## Input File Format Example

**Hourly data file (`china_sites_20230101.csv`):**
```csv
date,hour,type,1001A,1002A,1003A,...
20230101,0,PM2.5,16,13,18,...
20230101,1,PM2.5,15,14,17,...
...
20230101,23,PM2.5,17,15,16,...
```

**Station location file (`MonitorLatLonTable.csv`):**
```csv
ID,Lat,Lon,...
1001A,39.8784,116.3621,...
1002A,40.2915,116.2202,...
...
```

## Output File Format Example

**Daily monitoring file (`2023_DailyPM2.5Monitor.csv`):**
```csv
Site,Date,Conc,Valid_Hours,Actual_Hour_Count,Lat,Lon
1001A,2023-01-01,19.375,24,24,39.8784,116.3621
1002A,2023-01-01,17.667,24,24,40.2915,116.2202
...
```

**Hourly monitoring file (`2023_HourlyPM2.5Monitor.csv`):**
```csv
Site,Date,Conc,Lat,Lon
1001A,2023-01-01 00,16.0,39.8784,116.3621
1001A,2023-01-01 01,15.0,39.8784,116.3621
1001A,2023-01-01 02,14.5,39.8784,116.3621
...
1002A,2023-01-01 00,13.0,40.2915,116.2202
...
```

## Processing Statistics

After processing, the script outputs:
- Total days processed (days with >=20 valid hours)
- Total days skipped (days failing quality control)
- Valid stations per day
- Total valid records
- Time range processed
- Missing geographic coordinate warnings

## Troubleshooting

**Missing input files:**
- Verify data folder structure: `站点_YYYY0101-YYYY1231/站点_YYYY0101-YYYY12331/`
- Check file naming convention: `china_sites_YYYYMMDD.csv`
- Ensure data files contain PM2.5 hourly data (type="PM2.5")

**No valid data processed:**
- Check if hourly data has PM2.5 type values
- Verify data quality: check for sufficient valid hours (>=20)
- Review station IDs match between data files and MonitorLatLonTable.csv

**Missing geographic coordinates:**
- Ensure `MonitorLatLonTable.csv` exists in working directory
- Verify station IDs in data match IDs in MonitorLatLonTable.csv
- Check MonitorLatLonTable.csv has required columns: ID, Lat, Lon

**High number of skipped days:**
- Low data quality days (<20 valid hours) are normal
- Check source data completeness for problematic days
- Verify station network operational status during those periods

## Example Output

**Daily data only:**
```
共发现 365 个数据文件，开始处理...

2023-01-01：基于24个实际小时数计算平均值（仅有效小时数>=20的站点）
处理 2023-01-01：有效站点 1645/2026，跳过 381 个站点

...

=== 处理摘要 ===
成功处理天数：364
跳过低质量天数：1

=== 2023年 日均数据 最终结果 ===
时间范围：2023-01-01 至 2023-12-31
总有效天数：364
总有效站点数：2026
总有效记录数：737,740
结果文件路径：/path/to/2023_DailyPM2.5Monitor.csv
```

**Daily + Hourly data (with `--hourly` flag):**
```
共发现 365 个数据文件，开始处理...

2023-01-01：基于24个实际小时数计算平均值（仅有效小时数>=20的站点）
处理 2023-01-01：有效站点 1645/2026，跳过 381 个站点

...

=== 处理摘要 ===
成功处理天数：364
跳过低质量天数：1

=== 2023年 日均数据 最终结果 ===
时间范围：2023-01-01 至 2023-12-31
总有效天数：364
总有效站点数：2026
总有效记录数：737,740
结果文件路径：/path/to/2023_DailyPM2.5Monitor.csv

=== 2023年 小时数据 最终结果 ===
时间范围：2023-01-01 00 至 2023-12-31 23
总有效天数：364
总有效站点数：2026
总有效记录数：17,633,560
结果文件路径：/path/to/2023_HourlyPM2.5Monitor.csv
```

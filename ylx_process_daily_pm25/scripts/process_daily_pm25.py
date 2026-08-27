#!/usr/bin/env python3
"""
处理日均和小时级PM2.5监测数据的脚本

将站点小时PM2.5数据转换为日均浓度数据（有效小时数>=20），
可选输出小时级数据。

使用方法:
    python process_daily_pm25.py <year> [year2] [year3] ... [--workdir <path>] [--hourly]
"""

import pandas as pd
import numpy as np
import os
import sys
import argparse
from datetime import datetime


def calculate_site_data_availability_optimized(df, date_formatted):
    """计算每个站点的有效小时数（基于24小时标准）"""
    try:
        # 筛选PM2.5小时数据（hour在0-23之间）
        pm25_hourly_mask = (df['type'] == 'PM2.5') & (df['hour'].between(0, 23))
        pm25_hourly_df = df[pm25_hourly_mask]

        if pm25_hourly_df.empty:
            print(f"{date_formatted}：无PM2.5小时数据")
            return {}, {}, 0

        # 1. 统计当天实际的PM2.5小时记录数（用于参考）
        actual_hour_count = len(pm25_hourly_df)

        # 2. 获取所有站点列
        site_columns = [col for col in df.columns if col not in ['date', 'hour', 'type']]

        # 3. 计算各站点的有效小时数（而非比例）
        site_data = pm25_hourly_df[site_columns]
        valid_counts = site_data.notna().sum(axis=0)  # 有效小时数

        # 转换为是否满足24小时的83.3%（即>=20小时）
        availability_check = valid_counts >= 20  # 24 * 0.8333 ≈ 20

        return availability_check.to_dict(), valid_counts.to_dict(), actual_hour_count

    except Exception as e:
        print(f"计算站点数据有效率时出错：{str(e)}")
        return {}, {}, 0


def calculate_daily_average(df, availability_check, valid_counts):
    """仅对有效小时数>=20的站点计算PM2.5日均浓度"""
    # 筛选PM2.5小时数据
    pm25_hourly_mask = (df['type'] == 'PM2.5') & (df['hour'].between(0, 23))
    pm25_hourly_df = df[pm25_hourly_mask]

    if pm25_hourly_df.empty:
        return None

    site_columns = [col for col in df.columns if col not in ['date', 'hour', 'type']]
    daily_avg = {}

    # 仅对有效小时数>=20的站点计算平均值（24*83.3%≈20）
    for site in site_columns:
        if availability_check.get(site, False):
            hourly_values = pm25_hourly_df[site].dropna()
            daily_avg[site] = hourly_values.mean()

    return daily_avg


def process_daily_data_with_melt(file_path, output_hourly_data=False):
    """
    处理单个文件，全部使用小时数据计算日均浓度，有效标准为>=20小时（24*83.3%）

    参数:
        file_path: 输入文件路径
        output_hourly_data: 是否输出小时级数据

    返回:
        daily_df: 日均数据DataFrame
        hourly_df: 小时数据DataFrame（如果output_hourly_data为True）
    """
    try:
        df = pd.read_csv(file_path)

        # 提取并格式化日期
        file_name = os.path.basename(file_path)
        date_str = file_name.split('china_sites_')[1].split('.')[0]
        date_formatted = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')

        # 计算有效率（基于24小时的83.3%标准）
        availability_check, valid_counts, actual_hour_count = calculate_site_data_availability_optimized(df, date_formatted)
        if not availability_check:
            print(f"跳过 {date_formatted}：无有效PM2.5小时数据")
            return None, None

        # 使用小时数据计算日均浓度（仅有效小时数>=20的站点）
        daily_avg = calculate_daily_average(df, availability_check, valid_counts)
        if daily_avg is None or len(daily_avg) == 0:
            print(f"警告：{date_formatted} 无符合条件的站点（有效小时数>=20）可计算平均值")
            return None, None

        # 用计算的平均值创建临时行
        target_row = pd.DataFrame([daily_avg])
        print(f"{date_formatted}：基于{actual_hour_count}个实际小时数计算平均值（仅有效小时数>=20的站点）")

        # 确保临时行包含所有站点（无数据的站点设为NaN）
        site_columns = [col for col in df.columns if col not in ['date', 'hour', 'type']]
        for col in site_columns:
            if col not in target_row.columns:
                target_row[col] = np.nan

        # 重塑数据并过滤有效站点
        melted_data = target_row.melt(
            id_vars=[],
            value_vars=site_columns,
            var_name='Site',
            value_name='Conc'
        )
        # 过滤条件：浓度非空 + 有效小时数>=20
        valid_mask = melted_data['Site'].map(lambda x: availability_check.get(x, False))
        non_null_mask = melted_data['Conc'].notna()
        filtered_data = melted_data[valid_mask & non_null_mask].copy()

        if filtered_data.empty:
            print(f"警告：{date_formatted} 无满足条件的有效站点数据")
            return None, None

        # 补充日期和有效小时数信息
        filtered_data['Date'] = date_formatted
        filtered_data['Valid_Hours'] = filtered_data['Site'].map(valid_counts)  # 有效小时数
        filtered_data['Actual_Hour_Count'] = actual_hour_count  # 当天实际小时数

        # 输出有效站点统计
        total_sites = len(site_columns)
        valid_sites = len(filtered_data)
        skipped_sites = total_sites - valid_sites
        print(f"处理 {date_formatted}：有效站点 {valid_sites}/{total_sites}，跳过 {skipped_sites} 个站点\n")

        daily_df = filtered_data[['Site', 'Date', 'Conc', 'Valid_Hours', 'Actual_Hour_Count']]

        # 处理小时级数据
        hourly_df = None
        if output_hourly_data:
            # 筛选PM2.5小时数据
            pm25_hourly_mask = (df['type'] == 'PM2.5') & (df['hour'].between(0, 23))
            pm25_hourly_df = df[pm25_hourly_mask].copy()

            if not pm25_hourly_df.empty:
                # 重塑为长格式
                hourly_melted = pm25_hourly_df.melt(
                    id_vars=['date', 'hour'],
                    value_vars=site_columns,
                    var_name='Site',
                    value_name='Conc'
                )

                # 过滤有效值
                hourly_melted = hourly_melted[hourly_melted['Conc'].notna()].copy()

                # 格式化日期时间为 YYYY-MM-DD HH
                hourly_melted['datetime'] = (
                    pd.to_datetime(hourly_melted['date'], format='%Y%m%d').dt.strftime('%Y-%m-%d') +
                    ' ' +
                    hourly_melted['hour'].astype(str).str.zfill(2)
                )

                hourly_df = hourly_melted[['Site', 'datetime', 'Conc']]
                hourly_df = hourly_df.rename(columns={'datetime': 'Date'})

        return daily_df, hourly_df

    except Exception as e:
        print(f"处理文件 {os.path.basename(file_path)} 出错：{str(e)}\n")
        return None, None


def process_year(year, workdir, output_hourly=False):
    """
    处理指定年份的日均PM2.5数据，可选择输出小时级数据

    参数:
        year: 年份 (如 2023)
        workdir: 工作目录
        output_hourly: 是否输出小时级数据

    返回:
        success: 是否成功
        output_path: 输出文件路径
        hourly_output_path: 小时数据输出路径（如果output_hourly为True）
    """
    print(f"\n{'='*60}")
    print(f"处理 {year} 年数据")
    if output_hourly:
        print(f"（同时输出小时级数据）")
    print(f"{'='*60}\n")

    # 配置路径
    data_folder = os.path.join(workdir, f"站点_{year}0101-{year}1231", f"站点_{year}0101-{year}1231")
    output_path = os.path.join(workdir, f"{year}_DailyPM2.5Monitor.csv")
    hourly_output_path = os.path.join(workdir, f"{year}_HourlyPM2.5Monitor.csv") if output_hourly else None
    lat_lon_path = os.path.join(workdir, "MonitorLatLonTable.csv")

    # 检查数据文件夹
    if not os.path.exists(data_folder):
        print(f"错误：数据文件夹不存在 - {data_folder}")
        return False, None, None

    # 筛选CSV文件
    all_files = [f for f in os.listdir(data_folder) if "china_sites_" in f and f.endswith('.csv')]
    if not all_files:
        print(f"未在 {data_folder} 中找到符合条件的CSV文件")
        return False, None, None
    all_files.sort()
    print(f"共发现 {len(all_files)} 个数据文件，开始处理...\n")

    # 批量处理文件（全部使用小时数据计算，有效标准为>=20小时）
    all_daily_data = []
    all_hourly_data = [] if output_hourly else None
    total_processed = 0
    total_skipped = 0

    for file in all_files:
        file_path = os.path.join(data_folder, file)
        daily_df, hourly_df = process_daily_data_with_melt(file_path, output_hourly_data=output_hourly)
        if daily_df is not None:
            all_daily_data.append(daily_df)
            if output_hourly and hourly_df is not None:
                all_hourly_data.append(hourly_df)
            total_processed += 1
        else:
            total_skipped += 1

    # 输出处理摘要
    print(f"\n=== {year}年 处理摘要 ===")
    print(f"成功处理天数：{total_processed}")
    print(f"跳过低质量天数：{total_skipped}")

    if not all_daily_data:
        print(f"未提取到任何有效数据，{year}年处理失败")
        return False, None, None

    # 合并日均数据并补充经纬度
    conc_df = pd.concat(all_daily_data, ignore_index=True)
    if os.path.exists(lat_lon_path):
        lat_lon_df = pd.read_csv(lat_lon_path)
        if set(['ID', 'Lat', 'Lon']).issubset(lat_lon_df.columns):
            lat_lon_df.rename(columns={'ID': 'Site'}, inplace=True)
            conc_df = pd.merge(conc_df, lat_lon_df[['Site', 'Lat', 'Lon']], on='Site', how='left')
            missing_geo = conc_df[conc_df['Lat'].isna()]['Site'].nunique()
            if missing_geo > 0:
                print(f"警告：有 {missing_geo} 个站点未匹配到经纬度数据")
        else:
            print("警告：经纬度表缺少必要列（ID/Lat/Lon），不补充地理信息")
    else:
        print("警告：未找到经纬度表，不补充地理信息")

    # 保存日均结果
    conc_df.to_csv(output_path, index=False)

    # 输出最终统计（日均数据）
    print(f"\n=== {year}年 日均数据 最终结果 ===")
    print(f"时间范围：{conc_df['Date'].min()} 至 {conc_df['Date'].max()}")
    print(f"总有效天数：{conc_df['Date'].nunique()}")
    print(f"总有效站点数：{conc_df['Site'].nunique()}")
    print(f"总有效记录数：{len(conc_df):,}")
    print(f"结果文件路径：{output_path}")

    # 处理小时级数据
    if output_hourly and all_hourly_data:
        # 合并小时数据并补充经纬度
        hourly_df = pd.concat(all_hourly_data, ignore_index=True)
        if os.path.exists(lat_lon_path):
            lat_lon_df_for_hourly = pd.read_csv(lat_lon_path)
            if set(['ID', 'Lat', 'Lon']).issubset(lat_lon_df_for_hourly.columns):
                lat_lon_df_for_hourly.rename(columns={'ID': 'Site'}, inplace=True)
                hourly_df = pd.merge(hourly_df, lat_lon_df_for_hourly[['Site', 'Lat', 'Lon']], on='Site', how='left')

        # 保存小时结果
        hourly_df.to_csv(hourly_output_path, index=False)

        # 输出最终统计（小时数据）
        print(f"\n=== {year}年 小时数据 最终结果 ===")
        print(f"时间范围：{hourly_df['Date'].min()} 至 {hourly_df['Date'].max()}")
        print(f"总有效天数：{hourly_df['Date'].str.split(' ').str[0].nunique()}")
        print(f"总有效站点数：{hourly_df['Site'].nunique()}")
        print(f"总有效记录数：{len(hourly_df):,}")
        print(f"结果文件路径：{hourly_output_path}")

        return True, output_path, hourly_output_path
    elif output_hourly:
        print(f"\n警告：未提取到任何有效小时数据，{year}年小时数据生成失败")
        return True, output_path, None

    return True, output_path, None


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='处理日均PM2.5监测数据，可选输出小时级数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python process_daily_pm25.py 2023
  python process_daily_pm25.py 2023 --hourly
  python process_daily_pm25.py 2023 2022 2021 --hourly
  python process_daily_pm25.py 2023 --workdir /path/to/working/directory --hourly
        """
    )
    parser.add_argument('years', type=int, nargs='+', help='要处理的年份（可指定多个）')
    parser.add_argument('--workdir', type=str, help='工作目录（默认为当前目录）')
    parser.add_argument('--hourly', action='store_true', help='同时输出小时级数据文件')

    args = parser.parse_args()

    # 设置工作目录
    if args.workdir:
        workdir = os.path.abspath(args.workdir)
    else:
        workdir = os.getcwd()

    print(f"工作目录: {workdir}\n")
    if args.hourly:
        print(f"小时级数据输出: 启用\n")

    # 处理所有指定年份
    results = []
    for year in args.years:
        if year < 2000 or year > 2100:
            print(f"错误：年份 {year} 必须在2000-2100之间")
            continue

        success, output_path, hourly_output_path = process_year(year, workdir, output_hourly=args.hourly)
        results.append({
            'year': year,
            'success': success,
            'output_path': output_path,
            'hourly_output_path': hourly_output_path
        })

    # 输出总体结果
    print(f"\n{'='*60}")
    print(f"所有年份处理完成")
    print(f"{'='*60}\n")

    success_count = sum(1 for r in results if r['success'])
    total_count = len(results)

    print(f"成功：{success_count}/{total_count} 年")

    for result in results:
        status = "✓" if result['success'] else "✗"
        print(f"  {status} {result['year']}:")
        print(f"      日均: {result['output_path'] or '失败'}")
        if args.hourly:
            print(f"      小时: {result['hourly_output_path'] or '失败'}")

    # 返回退出码
    sys.exit(0 if success_count == total_count else 1)


if __name__ == "__main__":
    main()

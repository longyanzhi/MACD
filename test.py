import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# ===================== 1. 读取数据并绘制时间-温度曲线 =====================
file_path = r"C:\Users\35223\MACD\experiment1.xlsx"
df = pd.read_excel(file_path, header=0)

# 提取数据（适配你的表头：t、0.2、0.4、0.6、0.8）
time = df['t'].values                # 时间列
temp_20 = df[0.2].values             # 20% Sn温度
temp_40 = df[0.4].values             # 40% Sn温度
temp_60 = df[0.6].values             # 60% Sn温度
temp_80 = df[0.8].values             # 80% Sn温度

# 绘制时间-温度冷却曲线图
plt.figure(figsize=(10, 5))
plt.plot(time, temp_20, label='20% Sn')
plt.plot(time, temp_40, label='40% Sn')
plt.plot(time, temp_60, label='60% Sn')
plt.plot(time, temp_80, label='80% Sn')

plt.xlabel('Time (s)')
plt.ylabel('Temperature (°C)')
plt.title('Time-Temperature Cooling Curves')
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('Cooling_Curves.png', dpi=300)
plt.show()

# ===================== 2. 纯理论Sn-Pb相图（无任何实验点） =====================
# 标准相图参数（材料科学公认值）
Pb_melt = 327.5    # 纯Pb熔点 (0% Sn)
Sn_melt = 231.0    # 纯Sn熔点 (100% Sn)
eutc_comp = 61.9   # 共晶成分 (61.9% Sn)
eutc_temp = 183    # 共晶温度

plt.figure(figsize=(10, 6))

# ① 左液相线：纯Pb → 共晶点（蓝色实线）
plt.plot([0, eutc_comp], [Pb_melt, eutc_temp], 'b-', linewidth=3, label='Left Liquidus (Pb side)')

# ② 右液相线：纯Sn → 共晶点（红色实线）
plt.plot([100, eutc_comp], [Sn_melt, eutc_temp], 'r-', linewidth=3, label='Right Liquidus (Sn side)')

# ③ 共晶线：183°C水平线（修复参数错误：颜色和线型分开传）
plt.hlines(
    y=eutc_temp,          # 水平线y轴位置
    xmin=0, xmax=100,     # x轴范围
    color='g',            # 颜色：绿色
    linestyle='--',       # 线型：虚线（单独传，不再和颜色合并）
    linewidth=2,          # 线宽
    label=f'Eutectic Line {eutc_temp}°C'
)

# ④ 共晶点标记（金色实心点）
plt.scatter(eutc_comp, eutc_temp, c='gold', s=200, zorder=5, label='Eutectic Point')

# 图表基础设置
plt.xlabel('Sn Mole Fraction (%)')
plt.ylabel('Temperature (°C)')
plt.title('Sn-Pb Binary Phase Diagram (Theoretical)')
plt.xlim(0, 100)          # 横轴0-100% Sn
plt.ylim(150, 350)        # 纵轴覆盖共晶点到纯Pb熔点
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('Sn_Pb_Phase_Diagram_Pure_Theory.png', dpi=300)
plt.show()
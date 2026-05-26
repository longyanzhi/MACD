import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from scipy.stats import linregress

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ====================== 1. 输入实验数据 ======================
# 室温实验 (Run 1-7) 数据
# 列: Run, V_S2O8, V_S2SO4, V_S2O3, V_KI, delta_t, ln_1_over_dt
data_room = pd.DataFrame({
    'Run': [1, 2, 3, 4, 5, 6, 7],
    'V_S2O8': [10, 10, 10, 10, 8, 6, 4],  # (NH4)2S2O8 体积
    'V_KI':   [10, 8, 6, 4, 10, 10, 10],  # KI 体积
    'delta_t': [260, 281, 345, 690, 286, 405, 730]  # 反应时间
})

# 温度实验数据
# 列: Run, T_C, delta_t
data_temp = pd.DataFrame({
    'Run': ['1', '1b', '1a'],
    'T_C': [14, 30, 45],
    'delta_t': [260, 189, 69]
})

# 计算 ln(1/delta_t)
data_room['ln_1_over_dt'] = np.log(1 / data_room['delta_t'])
data_temp['ln_1_over_dt'] = np.log(1 / data_temp['delta_t'])
data_temp['T_K'] = data_temp['T_C'] + 273.15
data_temp['1_over_T'] = 1 / data_temp['T_K']

# ====================== 2. 计算反应级数 n (对 I⁻) ======================
# 条件: V_S2O8 不变 (Run 1-4, V_S2O8=10 cm³)
subset_n = data_room[data_room['V_S2O8'] == 10].copy()
subset_n['ln_V_KI'] = np.log(subset_n['V_KI'])

# 线性回归: ln(1/Δt) vs ln(V_KI)
X_n = subset_n['ln_V_KI'].values.reshape(-1, 1)
y_n = subset_n['ln_1_over_dt'].values
reg_n = LinearRegression().fit(X_n, y_n)
n = reg_n.coef_[0]
intercept_n = reg_n.intercept_
r2_n = reg_n.score(X_n, y_n)

print(f"=== 对 I⁻ 的反应级数 n ===")
print(f"n = {n:.3f}, R² = {r2_n:.3f}")

# 绘图
plt.figure(figsize=(6, 4))
plt.scatter(subset_n['ln_V_KI'], subset_n['ln_1_over_dt'], color='blue', label='Data points')
x_fit = np.linspace(subset_n['ln_V_KI'].min(), subset_n['ln_V_KI'].max(), 100)
y_fit = reg_n.predict(x_fit.reshape(-1, 1))
plt.plot(x_fit, y_fit, 'r--', label=f'Fit: slope = {n:.2f}')
plt.xlabel(r'$\ln(V(I^-))$')
plt.ylabel(r'$\ln(1/\Delta t)$')
plt.title('Determination of reaction order n ')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('reaction_order_n.png', dpi=300)
plt.show()

# ====================== 3. 计算反应级数 m (对 S2O8²⁻) ======================
# 条件: V_KI 不变 (Run 1,5,6,7, V_KI=10 cm³)
subset_m = data_room[data_room['V_KI'] == 10].copy()
subset_m['ln_V_S2O8'] = np.log(subset_m['V_S2O8'])

# 线性回归: ln(1/Δt) vs ln(V_S2O8)
X_m = subset_m['ln_V_S2O8'].values.reshape(-1, 1)
y_m = subset_m['ln_1_over_dt'].values
reg_m = LinearRegression().fit(X_m, y_m)
m = reg_m.coef_[0]
intercept_m = reg_m.intercept_
r2_m = reg_m.score(X_m, y_m)

print(f"\n=== 对 S2O8²⁻ 的反应级数 m ===")
print(f"m = {m:.3f}, R² = {r2_m:.3f}")

# 绘图
plt.figure(figsize=(6, 4))
plt.scatter(subset_m['ln_V_S2O8'], subset_m['ln_1_over_dt'], color='green', label='Data points')
x_fit = np.linspace(subset_m['ln_V_S2O8'].min(), subset_m['ln_V_S2O8'].max(), 100)
y_fit = reg_m.predict(x_fit.reshape(-1, 1))
plt.plot(x_fit, y_fit, 'r--', label=f'Fit: slope = {m:.2f}')
plt.xlabel(r'$\ln(V(S_2O_8^{2-}))$')
plt.ylabel(r'$\ln(1/\Delta t)$')
plt.title('Determination of reaction order m')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('reaction_order_m.png', dpi=300)
plt.show()

# ====================== 4. 多元线性回归: 同时拟合 m, n, ln(k) ======================
# 构建自变量矩阵: ln(V_S2O8), ln(V_KI)
X_multi = np.log(data_room[['V_S2O8', 'V_KI']].values)
y_multi = data_room['ln_1_over_dt'].values
reg_multi = LinearRegression().fit(X_multi, y_multi)
m_multi, n_multi = reg_multi.coef_
ln_k = reg_multi.intercept_
k = np.exp(ln_k)
r2_multi = reg_multi.score(X_multi, y_multi)

print(f"\n=== 多元线性回归结果 ===")
print(f"m (S2O8²⁻) = {m_multi:.3f}")
print(f"n (I⁻) = {n_multi:.3f}")
print(f"ln(k) = {ln_k:.3f}")
print(f"k (relative) = {k:.3e}")
print(f"R² = {r2_multi:.3f}")

# ====================== 5. 阿伦尼乌斯图: 计算活化能 Ea ======================
# 线性回归: ln(1/Δt) vs 1/T (K⁻¹)
X_temp = data_temp['1_over_T'].values.reshape(-1, 1)
y_temp = data_temp['ln_1_over_dt'].values
reg_temp = LinearRegression().fit(X_temp, y_temp)
slope = reg_temp.coef_[0]
intercept_temp = reg_temp.intercept_
r2_temp = reg_temp.score(X_temp, y_temp)

R = 8.314  # J·mol⁻¹·K⁻¹
Ea = -slope * R  # J/mol
Ea_kJ = Ea / 1000  # kJ/mol

print(f"\n=== 活化能 Ea 计算 ===")
print(f"斜率 = {slope:.3f} K")
print(f"Ea = {Ea_kJ:.2f} kJ/mol")
print(f"R² = {r2_temp:.3f}")

# 绘图
plt.figure(figsize=(6, 4))
plt.scatter(data_temp['1_over_T'], data_temp['ln_1_over_dt'], color='red', label='Data points')
x_fit = np.linspace(data_temp['1_over_T'].min(), data_temp['1_over_T'].max(), 100)
y_fit = reg_temp.predict(x_fit.reshape(-1, 1))
plt.plot(x_fit, y_fit, 'b--', label=f'Fit: slope = {slope:.0f} K')
plt.xlabel(r'$1/T$ (1/K)')
plt.ylabel(r'$\ln(1/\Delta t)$')
plt.title('Arrhenius plot for activation energy')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('arrhenius_plot.png', dpi=300)
plt.show()

print("\n=== 所有图已保存为: reaction_order_n.png, reaction_order_m.png, arrhenius_plot.png ===")
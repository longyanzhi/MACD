# ======================
# Tushare Token: 复制下面第4到7行代码，导入到项目代码中
# ======================
import tushare as ts
import tushare.pro.client as client
client.DataApi._DataApi__http_url = "http://tushare.xyz" # 一定要加上这行代码，否则会报错
pro = ts.pro_api('f8d313b7e099ffca1d87a7376b6d4b4ceca4b235326ff381f23a9de4') # 你的独立Token请勿泄露

# ======================
# 实时日线行情
# ======================
df = pro.rt_k(ts_code='00000*.SZ')
print("实时日线：")
print(df)
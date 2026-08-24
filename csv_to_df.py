import pandas as pd


pd.set_option('display.max_rows', None)  # Mostrar todas las filas
pd.set_option('display.max_columns', None) 
df = pd.read_csv('datos_extraidos.csv', quotechar='"', encoding="utf-8")
df.to_excel("archivo.xlsx", index=False)
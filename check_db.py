import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost", # 로컬에서 실행할 때는 localhost 혹은 127.0.0.1
        database="postgres",
        user="postgres",
        password="1234",
        port="5432"
    )
    print("✅ 성공: 토스 DB에 무사히 연결되었습니다!")
    conn.close()
except Exception as e:
    print(f"❌ 실패: 에러 발생 -> {e}")
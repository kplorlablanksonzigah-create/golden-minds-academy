import csv
import io
import sqlite3
from datetime import date
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__)
app.secret_key = 'golden_minds_secret_key_2026'


# --- DATABASE SETUP ---
def get_db_connection():
  conn = sqlite3.connect('school_database.db')
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  conn = get_db_connection()

  # Create students table
  conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            age INTEGER NOT NULL,
            tuition REAL DEFAULT 300.00,
            breakfast REAL DEFAULT 80.00,
            lunch REAL DEFAULT 120.00,
            transportation REAL DEFAULT 100.00,
            total_fee REAL DEFAULT 600.00
        )
    """)

  # Migrations
  for col, default_val in [
      ('tuition', 300.00),
      ('breakfast', 80.00),
      ('lunch', 120.00),
      ('transportation', 100.00),
  ]:
    try:
      conn.execute(
          f'ALTER TABLE students ADD COLUMN {col} REAL DEFAULT {default_val}'
      )
    except sqlite3.OperationalError:
      pass

  # Attendance table
  conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (id)
        )
    """)

  # Grades table
  conn.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            score INTEGER NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (id)
        )
    """)

  # Fee Payments table
  conn.execute("""
        CREATE TABLE IF NOT EXISTS fee_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            amount_paid REAL NOT NULL,
            date_paid TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (id)
        )
    """)
  conn.commit()
  conn.close()


init_db()


# --- PUBLIC & LOGIN / LOGOUT ROUTES ---
@app.route('/')
def home():
  return render_template('index.html')


@app.route('/staff')
def staff_directory():
  return render_template('staff.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
  if request.method == 'POST':
    username = request.form['username']
    password = request.form['password']

    if username == 'admin' and password == 'password123':
      session['user'] = 'admin'
      session['role'] = 'admin'
      return redirect(url_for('admin_dashboard'))
    elif username == 'teacher' and password == 'password123':
      session['user'] = 'teacher'
      session['role'] = 'teacher'
      return redirect(url_for('teacher_dashboard'))
    elif username == 'accountant' and password == 'password123':
      session['user'] = 'accountant'
      session['role'] = 'accountant'
      return redirect(url_for('accounts_dashboard'))
    else:
      flash('Invalid username or password. Please try again.')

  return render_template('login.html')


@app.route('/logout')
def logout():
  session.clear()
  flash('You have been logged out successfully.')
  return redirect(url_for('login'))


# --- DASHBOARD ROUTES (SESSION PROTECTED) ---
@app.route('/admin_dashboard')
def admin_dashboard():
  if session.get('role') != 'admin':
    flash('Please log in as Administrator to access the Admin Portal.')
    return redirect(url_for('login'))

  conn = get_db_connection()
  students = conn.execute('SELECT * FROM students').fetchall()
  conn.close()
  return render_template('admin_dashboard.html', students=students)


@app.route('/teacher_dashboard')
def teacher_dashboard():
  if session.get('role') != 'teacher':
    flash('Please log in as Teacher to access the Teacher Portal.')
    return redirect(url_for('login'))

  today = str(date.today())
  conn = get_db_connection()

  students = conn.execute(
      """
        SELECT s.id, s.name, s.grade, s.age, a.status 
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id AND a.date = ?
    """,
      (today,),
  ).fetchall()

  all_grades = conn.execute(
      'SELECT student_id, subject, score FROM grades'
  ).fetchall()

  grades_dict = {}
  for g in all_grades:
    sid = g['student_id']
    if sid not in grades_dict:
      grades_dict[sid] = []
    grades_dict[sid].append({'subject': g['subject'], 'score': g['score']})

  conn.close()
  return render_template(
      'teacher_dashboard.html',
      students=students,
      today=today,
      grades=grades_dict,
  )


@app.route('/accounts_dashboard')
def accounts_dashboard():
  if session.get('role') != 'accountant':
    flash('Please log in as Accountant to access the Accounts Portal.')
    return redirect(url_for('login'))

  conn = get_db_connection()

  students = conn.execute("""
        SELECT s.id, s.name, s.grade, 
               COALESCE(s.tuition, 300.00) as tuition,
               COALESCE(s.breakfast, 80.00) as breakfast,
               COALESCE(s.lunch, 120.00) as lunch,
               COALESCE(s.transportation, 100.00) as transportation,
               (COALESCE(s.tuition, 300.00) + COALESCE(s.breakfast, 80.00) + COALESCE(s.lunch, 120.00) + COALESCE(s.transportation, 100.00)) as total_fee,
               COALESCE(SUM(p.amount_paid), 0) as paid
        FROM students s
        LEFT JOIN fee_payments p ON s.id = p.student_id
        GROUP BY s.id
    """).fetchall()

  recent_payments = conn.execute("""
        SELECT p.id as payment_id, p.amount_paid, p.date_paid, s.name as student_name, s.grade
        FROM fee_payments p
        JOIN students s ON p.student_id = s.id
        ORDER BY p.id DESC LIMIT 10
    """).fetchall()

  total_expected = sum(s['total_fee'] for s in students) if students else 0
  total_collected = sum(s['paid'] for s in students) if students else 0
  total_outstanding = total_expected - total_collected

  conn.close()
  return render_template(
      'accounts_dashboard.html',
      students=students,
      recent_payments=recent_payments,
      total_expected=total_expected,
      total_collected=total_collected,
      total_outstanding=total_outstanding,
  )


# --- EDIT STUDENT ROUTE ---
@app.route('/edit_student/<int:id>', methods=['GET', 'POST'])
def edit_student(id):
  if session.get('role') != 'admin':
    flash('Unauthorized access.')
    return redirect(url_for('login'))

  conn = get_db_connection()

  if request.method == 'POST':
    name = request.form['name']
    grade = request.form['grade']
    age = request.form['age']
    tuition = float(request.form['tuition'])
    breakfast = float(request.form['breakfast'])
    lunch = float(request.form['lunch'])
    transportation = float(request.form['transportation'])
    total_fee = tuition + breakfast + lunch + transportation

    conn.execute(
        """
            UPDATE students 
            SET name = ?, grade = ?, age = ?, tuition = ?, breakfast = ?, lunch = ?, transportation = ?, total_fee = ?
            WHERE id = ?
        """,
        (
            name,
            grade,
            age,
            tuition,
            breakfast,
            lunch,
            transportation,
            total_fee,
            id,
        ),
    )
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

  student = conn.execute(
      'SELECT * FROM students WHERE id = ?', (id,)
  ).fetchone()
  conn.close()

  if not student:
    return 'Student not found', 404

  return render_template('edit_student.html', student=student)


# --- EXPORT CSV ROUTES ---
@app.route('/export_fees_csv')
def export_fees_csv():
  if session.get('role') != 'accountant' and session.get('role') != 'admin':
    flash('Unauthorized access.')
    return redirect(url_for('login'))

  conn = get_db_connection()
  students = conn.execute("""
        SELECT s.id, s.name, s.grade, 
               COALESCE(s.tuition, 300.00) as tuition,
               COALESCE(s.breakfast, 80.00) as breakfast,
               COALESCE(s.lunch, 120.00) as lunch,
               COALESCE(s.transportation, 100.00) as transportation,
               (COALESCE(s.tuition, 300.00) + COALESCE(s.breakfast, 80.00) + COALESCE(s.lunch, 120.00) + COALESCE(s.transportation, 100.00)) as total_fee,
               COALESCE(SUM(p.amount_paid), 0) as paid
        FROM students s
        LEFT JOIN fee_payments p ON s.id = p.student_id
        GROUP BY s.id
    """).fetchall()
  conn.close()

  output = io.StringIO()
  writer = csv.writer(output)
  writer.writerow([
      'Student ID',
      'Full Name',
      'Grade',
      'Tuition (GHS)',
      'Breakfast (GHS)',
      'Lunch (GHS)',
      'Transport (GHS)',
      'Total Fee (GHS)',
      'Paid (GHS)',
      'Balance (GHS)',
      'Status',
  ])

  for s in students:
    balance = s['total_fee'] - s['paid']
    status = (
        'Paid' if balance <= 0 else ('Partial' if s['paid'] > 0 else 'Owing')
    )
    writer.writerow([
        f'GMA-{s["id"]:03d}',
        s['name'],
        s['grade'],
        f'{s["tuition"]:.2f}',
        f'{s["breakfast"]:.2f}',
        f'{s["lunch"]:.2f}',
        f'{s["transportation"]:.2f}',
        f'{s["total_fee"]:.2f}',
        f'{s["paid"]:.2f}',
        f'{balance:.2f}',
        status,
    ])

  output.seek(0)
  return Response(
      output.getvalue(),
      mimetype='text/csv',
      headers={
          'Content-Disposition': 'attachment;filename=Golden_Minds_Fee_Report.csv'
      },
  )


# --- REPORT CARD & RECEIPT ROUTES ---
@app.route('/report_card/<int:student_id>')
def report_card(student_id):
  conn = get_db_connection()
  student = conn.execute(
      'SELECT * FROM students WHERE id = ?', (student_id,)
  ).fetchone()

  if not student:
    conn.close()
    return 'Student not found', 404

  grades = conn.execute(
      'SELECT subject, score FROM grades WHERE student_id = ?', (student_id,)
  ).fetchall()

  total_score = sum(g['score'] for g in grades) if grades else 0
  average_score = round(total_score / len(grades), 1) if grades else 0

  present_days = conn.execute(
      "SELECT COUNT(*) FROM attendance WHERE student_id = ? AND status ="
      " 'Present'",
      (student_id,),
  ).fetchone()[0]

  absent_days = conn.execute(
      "SELECT COUNT(*) FROM attendance WHERE student_id = ? AND status ="
      " 'Absent'",
      (student_id,),
  ).fetchone()[0]

  conn.close()

  return render_template(
      'report_card.html',
      student=student,
      grades=grades,
      average_score=average_score,
      present_days=present_days,
      absent_days=absent_days,
  )


@app.route('/receipt/<int:payment_id>')
def view_receipt(payment_id):
  conn = get_db_connection()
  payment = conn.execute(
      """
        SELECT p.id as payment_id, p.amount_paid, p.date_paid, 
               s.id as student_id, s.name, s.grade, 
               COALESCE(s.tuition, 300.00) as tuition,
               COALESCE(s.breakfast, 80.00) as breakfast,
               COALESCE(s.lunch, 120.00) as lunch,
               COALESCE(s.transportation, 100.00) as transportation,
               (COALESCE(s.tuition, 300.00) + COALESCE(s.breakfast, 80.00) + COALESCE(s.lunch, 120.00) + COALESCE(s.transportation, 100.00)) as total_fee
        FROM fee_payments p
        JOIN students s ON p.student_id = s.id
        WHERE p.id = ?
    """,
      (payment_id,),
  ).fetchone()

  if not payment:
    conn.close()
    return 'Receipt not found', 404

  total_paid = conn.execute(
      'SELECT COALESCE(SUM(amount_paid), 0) FROM fee_payments WHERE student_id'
      ' = ?',
      (payment['student_id'],),
  ).fetchone()[0]

  conn.close()
  balance = payment['total_fee'] - total_paid

  return render_template(
      'receipt.html', payment=payment, total_paid=total_paid, balance=balance
  )


# --- ACTIONS ---
@app.route('/add_student', methods=['POST'])
def add_student():
  if session.get('role') != 'admin':
    flash('Unauthorized action.')
    return redirect(url_for('login'))

  name = request.form['name']
  grade = request.form['grade']
  age = request.form['age']

  conn = get_db_connection()
  conn.execute(
      'INSERT INTO students (name, grade, age, tuition, breakfast, lunch,'
      ' transportation, total_fee) VALUES (?, ?, ?, 300.00, 80.00, 120.00,'
      ' 100.00, 600.00)',
      (name, grade, age),
  )
  conn.commit()
  conn.close()

  return redirect(url_for('admin_dashboard'))


@app.route('/delete_student/<int:id>', methods=['POST'])
def delete_student(id):
  if session.get('role') != 'admin':
    flash('Unauthorized action.')
    return redirect(url_for('login'))

  conn = get_db_connection()
  conn.execute('DELETE FROM students WHERE id = ?', (id,))
  conn.execute('DELETE FROM attendance WHERE student_id = ?', (id,))
  conn.execute('DELETE FROM grades WHERE student_id = ?', (id,))
  conn.execute('DELETE FROM fee_payments WHERE student_id = ?', (id,))
  conn.commit()
  conn.close()

  return redirect(url_for('admin_dashboard'))


@app.route('/mark_attendance/<int:student_id>', methods=['POST'])
def mark_attendance(student_id):
  if session.get('role') != 'teacher':
    flash('Unauthorized action.')
    return redirect(url_for('login'))

  today = str(date.today())
  status = request.form.get('status', 'Present')

  conn = get_db_connection()
  conn.execute(
      'DELETE FROM attendance WHERE student_id = ? AND date = ?',
      (student_id, today),
  )
  conn.execute(
      'INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)',
      (student_id, today, status),
  )
  conn.commit()
  conn.close()

  return redirect(url_for('teacher_dashboard'))


@app.route('/add_grade/<int:student_id>', methods=['POST'])
def add_grade(student_id):
  if session.get('role') != 'teacher':
    flash('Unauthorized action.')
    return redirect(url_for('login'))

  subject = request.form['subject']
  score = request.form['score']

  conn = get_db_connection()
  conn.execute(
      'INSERT INTO grades (student_id, subject, score) VALUES (?, ?, ?)',
      (student_id, subject, score),
  )
  conn.commit()
  conn.close()

  return redirect(url_for('teacher_dashboard'))


@app.route('/record_payment/<int:student_id>', methods=['POST'])
def record_payment(student_id):
  if session.get('role') != 'accountant':
    flash('Unauthorized action.')
    return redirect(url_for('login'))

  amount = float(request.form['amount'])
  today = str(date.today())

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      'INSERT INTO fee_payments (student_id, amount_paid, date_paid) VALUES'
      ' (?, ?, ?)',
      (student_id, amount, today),
  )
  payment_id = cursor.lastrowid
  conn.commit()
  conn.close()

  return redirect(url_for('view_receipt', payment_id=payment_id))


if __name__ == '__main__':
  app.run(debug=True)
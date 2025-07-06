import os
import logging
import datetime
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List
from dotenv import load_dotenv
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.error import Conflict
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from bson import ObjectId

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
MONGODB_URI = os.getenv('MONGODB_URI')
PORT = int(os.getenv('PORT', 8080))

# MongoDB setup
client = MongoClient(MONGODB_URI)
db = client.attendance_bot
employees = db.employees
attendance = db.attendance
holidays = db.holidays

# Create indexes
employees.create_index("name")
attendance.create_index([("employee_id", 1), ("date", 1)], unique=True)
holidays.create_index("date", unique=True)

# States for conversation
SELECTING_ACTION, MARKING_ATTENDANCE, GETTING_REASON = range(3)

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- HTTP Server for Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Attendance Bot is running')

def run_http_server():
    server = HTTPServer(('', PORT), HealthCheckHandler)
    logger.info(f"HTTP server running on port {PORT}")
    server.serve_forever()

# --- Date Utilities ---
def parse_date(date_str: str) -> datetime.date:
    """Parse date from DD-MM-YYYY format"""
    try:
        return datetime.datetime.strptime(date_str, "%d-%m-%Y").date()
    except ValueError:
        raise ValueError("Invalid date format. Use DD-MM-YYYY")

def format_date(date: datetime.date) -> str:
    """Format date to DD-MM-YYYY string"""
    return date.strftime("%d-%m-%Y")

def format_date_long(date: datetime.date) -> str:
    """Format date to DD MMM YYYY string (e.g., 15-Jul-2025)"""
    return date.strftime("%d-%b-%Y")

def format_date_short(date: datetime.date) -> str:
    """Format date to DD MMM (e.g., 15-Jul)"""
    return date.strftime("%d-%b")

def validate_date(date_str: str) -> bool:
    """Check if date string is in DD-MM-YYYY format"""
    return bool(re.match(r'^\d{2}-\d{2}-\d{4}$', date_str))

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized access")
        return
    await update.message.reply_text(
        "*🌟 Welcome to Attendance Tracker\\!*\n\n"
        "Your all\\-in\\-one solution for staff management\n\n"
        "*🚀 Quick Start Guide*\n"
        "1\\. Add team: /add\\_employee \\[Name\\]\n"
        "2\\. Record attendance: /mark\\_attendance\n"
        "3\\. View reports: /daily\\_report or /monthly\\_report\n\n"
        "Type /help for full command list",
        parse_mode="MarkdownV2"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
*🔍 Attendance Bot Help Menu*

*Employee Management*
▫️ /add\\_employee \\[Name\\] \\- Add new staff
▫️ /list\\_employees \\- Show active team
▫️ /remove\\_employee \\[ID\\] \\- Remove staff

*Attendance Tracking*
▫️ /mark\\_attendance \\- Record daily attendance
▫️ /multiday\\_absence \\[ID\\] \\[Start\\] \\[End\\] \\[Reason\\] \\- Bulk absence
  Example: /multiday\\_absence 2 15\\-07\\-2025 18\\-07\\-2025 "Vacation"

*Reports*
▫️ /daily\\_report \\- Today's summary
▫️ /date\\_report \\[DD\\-MM\\-YYYY\\] \\- Specific date report
▫️ /last\\_7\\_days \\- Weekly summary
▫️ /last\\_30\\_days \\- Monthly summary
▫️ /monthly\\_report \\- Calendar month report
▫️ /employee\\_report \\[ID\\] \\- Individual performance

*Holiday Management*
▫️ /mark\\_holiday \\[Description\\] \\- Mark holiday
▫️ /list\\_holidays \\- View all holidays
▫️ /remove\\_holiday \\[DD\\-MM\\-YYYY\\] \\- Delete holiday

📅 _All dates use DD\\-MM\\-YYYY format_
💡 Tip: Use /list\\_employees to get staff IDs
    """
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")
    
async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /add_employee John Doe")
        return
    
    name = " ".join(context.args)
    try:
        result = employees.insert_one({"name": name, "active": True})
        # Clear employee map to force refresh
        if 'employee_map' in context.user_data:
            del context.user_data['employee_map']
        await update.message.reply_text(f"✅ Added new employee: {name}")
    except Exception as e:
        logger.error(f"Error adding employee: {e}")
        await update.message.reply_text("❌ Failed to add employee")

async def list_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    employee_list = list(employees.find({"active": True}, {"_id": 1, "name": 1}))
    
    if not employee_list:
        await update.message.reply_text("No employees found")
        return
    
    # Create simple sequential IDs
    response = "👥 *Employee List*\n"
    employee_map = {}
    
    for idx, emp in enumerate(employee_list, 1):
        # Store mapping of simple ID to ObjectId
        employee_map[str(idx)] = str(emp['_id'])
        response += f"#{idx}: {emp['name']}\n"
    
    # Store mapping in context
    context.user_data['employee_map'] = employee_map
    await update.message.reply_text(response, parse_mode="Markdown")

async def remove_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        simple_id = context.args[0]
        
        # Get employee mapping
        employee_map = context.user_data.get('employee_map', {})
        
        if not employee_map:
            await update.message.reply_text("❌ Employee list not loaded. Use /list_employees first.")
            return
            
        emp_id = employee_map.get(simple_id)
        
        if not emp_id:
            await update.message.reply_text("❌ Invalid employee ID")
            return
            
        result = employees.update_one(
            {"_id": ObjectId(emp_id)}, 
            {"$set": {"active": False}}
        )
        
        if result.modified_count == 0:
            await update.message.reply_text("❌ Employee not found")
        else:
            await update.message.reply_text(f"✅ Removed employee #{simple_id}")
            # Refresh employee map
            if 'employee_map' in context.user_data:
                del context.user_data['employee_map']
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /remove_employee [id]")
    except Exception as e:
        logger.error(f"Error removing employee: {e}")
        await update.message.reply_text("❌ Failed to remove employee")

# --- Attendance Flow ---
async def mark_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    # Check if today is Sunday
    if datetime.date.today().weekday() == 6:  # Sunday
        await update.message.reply_text("⛔ Sunday: Attendance not required")
        return
    
    today = datetime.date.today()
    today_str = format_date(today)
    
    # Check if holiday
    if holidays.find_one({"date": today_str}):
        await update.message.reply_text("⛔ Today is a holiday")
        return
    
    # Get active employees
    employee_list = list(employees.find({"active": True}, {"_id": 1, "name": 1}))
    
    if not employee_list:
        await update.message.reply_text("❌ No active employees")
        return ConversationHandler.END
    
    # Create simple ID mapping for attendance flow
    attendance_map = {}
    for idx, emp in enumerate(employee_list, 1):
        attendance_map[str(idx)] = str(emp['_id'])
    
    # Store employees in context
    context.user_data['attendance_flow'] = {
        'employees': employee_list,
        'attendance_map': attendance_map,  # Store mapping
        'current_index': 0,
        'attendance': {}
    }
    
    # Start with first employee
    emp = employee_list[0]
    keyboard = [
        [
            InlineKeyboardButton("✅ Present", callback_data=f"present_1"),  # Use simple ID
            InlineKeyboardButton("❌ Absent", callback_data=f"absent_1")
        ]
    ]
    await update.message.reply_text(
        f"🧑‍💼 *Employee #1: {emp['name']}*\n"
        f"📅 Date: {format_date_long(today)}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return MARKING_ATTENDANCE

async def handle_attendance_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_data = context.user_data['attendance_flow']
    employee_list = user_data['employees']
    current_index = user_data['current_index']
    attendance_map = user_data['attendance_map']
    
    # Process selection
    status, simple_id = data.split('_')
    emp_id = attendance_map[simple_id]
    user_data['attendance'][emp_id] = {'status': status}
    
    # If absent, ask for reason
    if status == 'absent':
        user_data['current_employee'] = emp_id
        user_data['current_simple_id'] = simple_id
        await query.edit_message_text("📝 *Reason for absence:*", parse_mode="Markdown")
        return GETTING_REASON
    
    # Move to next employee
    return await next_employee(update, context)

async def handle_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    user_data = context.user_data['attendance_flow']
    emp_id = user_data['current_employee']
    user_data['attendance'][emp_id]['reason'] = reason
    
    await update.message.reply_text("✅ Reason recorded")
    return await next_employee(update, context)

async def next_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data['attendance_flow']
    employee_list = user_data['employees']
    current_index = user_data['current_index'] + 1
    
    # Check if finished
    if current_index >= len(employee_list):
        return await finalize_attendance(update, context)
    
    # Show next employee
    user_data['current_index'] = current_index
    emp = employee_list[current_index]
    simple_id = str(current_index + 1)  # Simple ID is index + 1
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Present", callback_data=f"present_{simple_id}"),
            InlineKeyboardButton("❌ Absent", callback_data=f"absent_{simple_id}")
        ]
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            f"🧑‍💼 *Employee #{simple_id}: {emp['name']}*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.callback_query.edit_message_text(
            f"🧑‍💼 *Employee #{simple_id}: {emp['name']}*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    return MARKING_ATTENDANCE

async def finalize_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data['attendance_flow']
    today = datetime.date.today()
    today_str = format_date(today)
    
    # Save to database
    records = []
    for emp_id, data in user_data['attendance'].items():
        records.append({
            "employee_id": emp_id,
            "date": today_str,
            "status": data['status'],
            "reason": data.get('reason', "")
        })
    
    try:
        attendance.insert_many(records, ordered=False)
    except Exception as e:
        logger.error(f"Error saving attendance: {e}")
    
    # Cleanup
    del context.user_data['attendance_flow']
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🎉 *Attendance for {format_date_long(today)} recorded successfully!*",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# --- Reporting System ---
async def daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Today's attendance summary"""
    today = datetime.date.today()
    today_str = format_date(today)
    
    pipeline = [
        {"$match": {"date": today_str}},
        {"$lookup": {
            "from": "employees",
            "localField": "employee_id",
            "foreignField": "_id",
            "as": "employee"
        }},
        {"$unwind": "$employee"},
        {"$project": {
            "name": "$employee.name",
            "status": 1,
            "reason": 1
        }}
    ]
    
    records = list(attendance.aggregate(pipeline))
    
    # Count present/absent
    present_count = attendance.count_documents({"date": today_str, "status": "present"})
    absent_count = attendance.count_documents({"date": today_str, "status": "absent"})
    
    # Generate report
    report = f"📊 *Daily Report - {format_date_long(today)}*\n"
    report += f"✅ Present: {present_count} | ❌ Absent: {absent_count}\n\n"
    
    if records:
        report += "🧑‍💼 *Employee Details:*\n"
        for record in records:
            report += f"- {record['name']}: {'✅' if record['status'] == 'present' else '❌'}"
            if record.get('reason'):
                report += f" ({record['reason']})"
            report += "\n"
    else:
        report += "No attendance recorded today"
    
    await update.message.reply_text(report, parse_mode="Markdown")

async def date_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Report for specific date"""
    try:
        date_str = context.args[0]
        if not validate_date(date_str):
            await update.message.reply_text("❌ Invalid date format. Use DD-MM-YYYY")
            return
            
        target_date = parse_date(date_str)
        date_str_db = format_date(target_date)
        
        pipeline = [
            {"$match": {"date": date_str_db}},
            {"$lookup": {
                "from": "employees",
                "localField": "employee_id",
                "foreignField": "_id",
                "as": "employee"
            }},
            {"$unwind": "$employee"},
            {"$project": {
                "name": "$employee.name",
                "status": 1,
                "reason": 1
            }}
        ]
        
        records = list(attendance.aggregate(pipeline))
        
        # Count present/absent
        present_count = attendance.count_documents({"date": date_str_db, "status": "present"})
        absent_count = attendance.count_documents({"date": date_str_db, "status": "absent"})
        
        # Generate report
        report = f"📅 *Date Report - {format_date_long(target_date)}*\n"
        report += f"✅ Present: {present_count} | ❌ Absent: {absent_count}\n\n"
        
        if records:
            report += "🧑‍💼 *Employee Details:*\n"
            for record in records:
                report += f"- {record['name']}: {'✅' if record['status'] == 'present' else '❌'}"
                if record.get('reason'):
                    report += f" ({record['reason']})"
                report += "\n"
        else:
            report += "No attendance recorded on this date"
        
        await update.message.reply_text(report, parse_mode="Markdown")
    except IndexError:
        await update.message.reply_text("Usage: /date_report DD-MM-YYYY")
    except Exception as e:
        logger.error(f"Date report error: {e}")
        await update.message.reply_text("❌ Failed to generate report")

async def last_7_days_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rolling 7-day summary"""
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=6)
    await generate_period_report(update, start_date, end_date, "7 Days")

async def last_30_days_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rolling 30-day summary"""
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=29)
    await generate_period_report(update, start_date, end_date, "30 Days")

async def monthly_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monthly calendar report"""
    today = datetime.date.today()
    first_day = today.replace(day=1)
    last_day = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    
    # Convert dates to DD-MM-YYYY format for query
    first_day_str = format_date(first_day)
    last_day_str = format_date(last_day)
    
    # Get working days
    working_days = attendance.distinct("date", {
        "date": {"$gte": first_day_str, "$lte": last_day_str}
    })
    
    # Get holidays
    holiday_list = list(holidays.find({
        "date": {"$gte": first_day_str, "$lte": last_day_str}
    }, {"date": 1, "description": 1}))
    
    # Employee performance
    pipeline = [
        {"$match": {
            "date": {"$gte": first_day_str, "$lte": last_day_str},
        }},
        {"$group": {
            "_id": "$employee_id",
            "present_days": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}},
            "absent_days": {"$sum": {"$cond": [{"$eq": ["$status", "absent"]}, 1, 0]}},
            "total_days": {"$sum": 1}
        }},
        {"$lookup": {
            "from": "employees",
            "localField": "_id",
            "foreignField": "_id",
            "as": "employee"
        }},
        {"$unwind": "$employee"},
        {"$project": {
            "name": "$employee.name",
            "present_days": 1,
            "absent_days": 1,
            "percentage": {"$multiply": [
                {"$divide": ["$present_days", "$total_days"]},
                100
            ]}
        }}
    ]
    
    employee_performance = list(attendance.aggregate(pipeline))
    
    # Total counts
    total_present = sum(emp['present_days'] for emp in employee_performance)
    total_absent = sum(emp['absent_days'] for emp in employee_performance)
    
    # Generate report
    report = f"📈 *Monthly Report - {today.strftime('%B %Y')}*\n"
    report += f"📅 Period: {format_date_short(first_day)} to {format_date_short(last_day)}\n"
    report += f"📊 Working Days: {len(working_days)} | Holidays: {len(holiday_list)}\n"
    report += f"✅ Total Present: {total_present} | ❌ Total Absent: {total_absent}\n\n"
    
    report += "👥 *Employee Performance:*\n"
    for emp in sorted(employee_performance, key=lambda x: x['percentage'], reverse=True):
        report += f"- {emp['name']}: {emp.get('present_days', 0)}/{len(working_days)} "
        report += f"({emp.get('percentage', 0):.0f}%)"
        if emp.get('absent_days', 0) > 0:
            report += f" | ❌ Absences: {emp['absent_days']}"
        report += "\n"
    
    # Top absence reasons
    reason_pipeline = [
        {"$match": {
            "status": "absent",
            "reason": {"$ne": None, "$ne": ""},
            "date": {"$gte": first_day_str, "$lte": last_day_str}
        }},
        {"$group": {
            "_id": "$reason",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}},
        {"$limit": 3}
    ]
    
    top_reasons = list(attendance.aggregate(reason_pipeline))
    
    if top_reasons:
        report += "\n❌ *Top Absence Reasons:*\n"
        for reason in top_reasons:
            report += f"- {reason['_id']}: {reason['count']} time{'s' if reason['count'] > 1 else ''}\n"
    
    if holiday_list:
        report += "\n🗓️ *Holidays:*\n"
        for holiday in holiday_list:
            holiday_date = parse_date(holiday['date'])
            report += f"- {format_date_short(holiday_date)}: {holiday['description']}\n"
    
    await update.message.reply_text(report, parse_mode="Markdown")

async def generate_period_report(update: Update, start_date: datetime.date, 
                                end_date: datetime.date, period_name: str):
    """Generate report for custom period"""
    start_str = format_date(start_date)
    end_str = format_date(end_date)
    total_days = (end_date - start_date).days + 1
    
    pipeline = [
        {"$match": {
            "date": {"$gte": start_str, "$lte": end_str}
        }},
        {"$group": {
            "_id": "$employee_id",
            "present": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}},
            "absent": {"$sum": {"$cond": [{"$eq": ["$status", "absent"]}, 1, 0]}}
        }},
        {"$lookup": {
            "from": "employees",
            "localField": "_id",
            "foreignField": "_id",
            "as": "employee"
        }},
        {"$unwind": "$employee"},
        {"$project": {
            "name": "$employee.name",
            "present": 1,
            "absent": 1,
            "total": {"$sum": ["$present", "$absent"]},
            "rate": {"$multiply": [
                {"$divide": ["$present", {"$sum": ["$present", "$absent"]}]},
                100
            ]}
        }}
    ]
    
    results = list(attendance.aggregate(pipeline))
    
    # Calculate totals
    total_present = sum(r["present"] for r in results)
    total_absent = sum(r["absent"] for r in results)
    
    # Generate report
    report = f"📈 *{period_name} Report ({total_days} Days)*\n"
    report += f"📅 Period: {format_date_short(start_date)} to {format_date_short(end_date)}\n"
    report += f"✅ Total Present: {total_present} | ❌ Total Absent: {total_absent}\n\n"
    report += "🏆 *Top Performers*\n"
    
    # Sort by attendance rate descending
    top_performers = sorted(results, key=lambda x: x["rate"], reverse=True)[:3]
    for i, emp in enumerate(top_performers, 1):
        report += f"{i}. {emp['name']}: {emp['rate']:.0f}%\n"
    
    report += "\n⚠️ *Needs Improvement*\n"
    # Sort by attendance rate ascending
    needs_improvement = sorted(results, key=lambda x: x["rate"])[:3]
    for i, emp in enumerate(needs_improvement, 1):
        report += f"{i}. {emp['name']}: {emp['rate']:.0f}%\n"
    
    # Attendance distribution
    report += "\n📊 *Attendance Distribution*\n"
    report += f"✅ Present: {total_present} ({total_present/(total_present+total_absent)*100:.0f}%)\n"
    report += f"❌ Absent: {total_absent} ({total_absent/(total_present+total_absent)*100:.0f}%)\n"
    
    await update.message.reply_text(report, parse_mode="Markdown")

async def employee_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Individual performance report"""
    try:
        simple_id = context.args[0]
        employee_map = context.user_data.get('employee_map', {})
        
        if not employee_map:
            await update.message.reply_text("❌ Employee list not loaded. Use /list_employees first.")
            return
            
        emp_id = employee_map.get(simple_id)
        
        if not emp_id:
            await update.message.reply_text("❌ Invalid employee ID")
            return
            
        # Get employee details
        employee = employees.find_one({"_id": ObjectId(emp_id)})
        if not employee:
            await update.message.reply_text("❌ Employee not found")
            return
            
        # Last 30 days performance
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=29)
        start_str = format_date(start_date)
        end_str = format_date(end_date)
        
        pipeline = [
            {"$match": {
                "employee_id": emp_id,
                "date": {"$gte": start_str, "$lte": end_str}
            }},
            {"$group": {
                "_id": None,
                "present": {"$sum": {"$cond": [{"$eq": ["$status", "present"]}, 1, 0]}},
                "absent": {"$sum": {"$cond": [{"$eq": ["$status", "absent"]}, 1, 0]}}
            }}
        ]
        
        result = list(attendance.aggregate(pipeline))
        present = result[0]["present"] if result else 0
        absent = result[0]["absent"] if result else 0
        total = present + absent
        
        # Generate report
        report = f"👤 *Employee Report: {employee['name']}*\n"
        report += f"🆔 Employee ID: #{simple_id}\n\n"
        report += f"📅 Period: {format_date_short(start_date)} to {format_date_short(end_date)}\n"
        report += f"✅ Present: {present} days\n"
        report += f"❌ Absent: {absent} days\n"
        report += f"📊 Attendance Rate: {round((present/total)*100) if total > 0 else 0}%\n\n"
        
        # Attendance trend (last 7 days)
        trend_start = end_date - datetime.timedelta(days=6)
        trend_str = ""
        for i in range(7):
            day = trend_start + datetime.timedelta(days=i)
            day_str = format_date(day)
            record = attendance.find_one({"employee_id": emp_id, "date": day_str})
            if record:
                trend_str += "✅" if record['status'] == 'present' else "❌"
            else:
                trend_str += "⬜"
        report += f"📈 *Weekly Trend:*\n{trend_str}\n\n"
        
        report += f"📝 *Recent Absences:*\n"
        
        # Get last 3 absences with reasons
        absences = attendance.find({
            "employee_id": emp_id,
            "status": "absent"
        }).sort("date", -1).limit(3)
        
        if absences:
            for i, absence in enumerate(absences, 1):
                date_str = absence["date"]
                reason = absence.get("reason", "No reason provided")
                report += f"{i}. {date_str}: {reason}\n"
        else:
            report += "No absences in the last 30 days\n"
        
        await update.message.reply_text(report, parse_mode="Markdown")
    except IndexError:
        await update.message.reply_text("Usage: /employee_report [ID]")
    except Exception as e:
        logger.error(f"Employee report error: {e}")
        await update.message.reply_text("❌ Failed to generate report")

# --- Holiday Management ---
async def mark_holiday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        description = " ".join(context.args)
        if not description:
            raise ValueError
    except:
        await update.message.reply_text("Usage: /mark_holiday \"Holiday Name\"")
        return
    
    today = datetime.date.today()
    today_str = format_date(today)
    try:
        holidays.insert_one({
            "date": today_str,
            "description": description
        })
        await update.message.reply_text(f"🎉 Marked {format_date_long(today)} as holiday: {description}")
    except DuplicateKeyError:
        await update.message.reply_text(f"⚠️ {format_date_long(today)} is already marked as a holiday")
    except Exception as e:
        logger.error(f"Error marking holiday: {e}")
        await update.message.reply_text("❌ Failed to mark holiday")

async def list_holidays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    holiday_list = list(holidays.find().sort("date", 1))
    
    if not holiday_list:
        await update.message.reply_text("No holidays scheduled")
        return
    
    response = "🗓️ *Upcoming Holidays*\n" + "\n".join(
        [f"- {format_date_long(parse_date(hol['date']))}: {hol['description']}" 
         for hol in holiday_list]
    )
    await update.message.reply_text(response, parse_mode="Markdown")

async def remove_holiday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        if not context.args:
            raise ValueError
        
        date_str = context.args[0]
        if not validate_date(date_str):
            await update.message.reply_text("❌ Invalid date format. Use DD-MM-YYYY")
            return
            
        holiday_date = parse_date(date_str)
        date_str_formatted = format_date(holiday_date)
        result = holidays.delete_one({"date": date_str_formatted})
        
        if result.deleted_count == 0:
            await update.message.reply_text(f"❌ No holiday found on {format_date_long(holiday_date)}")
        else:
            await update.message.reply_text(f"✅ Removed holiday on {format_date_long(holiday_date)}")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /remove_holiday DD-MM-YYYY")
    except Exception as e:
        logger.error(f"Error removing holiday: {e}")
        await update.message.reply_text("❌ Failed to remove holiday")

# --- Multiday Absence ---
async def multiday_absence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    try:
        if len(context.args) < 3:
            raise ValueError
            
        simple_id = context.args[0]
        
        # Get employee mapping
        employee_map = context.user_data.get('employee_map', {})
        
        if not employee_map:
            await update.message.reply_text("❌ Employee list not loaded. Use /list_employees first.")
            return
            
        emp_id = employee_map.get(simple_id)
        
        if not emp_id:
            await update.message.reply_text("❌ Invalid employee ID")
            return
        
        # Validate and parse dates
        start_date_str = context.args[1]
        end_date_str = context.args[2]
        
        if not validate_date(start_date_str):
            await update.message.reply_text("❌ Invalid start date format. Use DD-MM-YYYY")
            return
        if not validate_date(end_date_str):
            await update.message.reply_text("❌ Invalid end date format. Use DD-MM-YYYY")
            return
            
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        
        reason = " ".join(context.args[3:]) if len(context.args) > 3 else "Not specified"
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Usage: /multiday_absence [id] [start_DD-MM-YYYY] [end_DD-MM-YYYY] [reason]"
        )
        return
    
    # Validate dates
    if start_date > end_date:
        await update.message.reply_text("❌ Error: Start date must be before end date")
        return
    
    # Process each day
    current_date = start_date
    days_processed = 0
    records = []
    
    while current_date <= end_date:
        # Skip Sundays and holidays
        if current_date.weekday() == 6:  # Sunday
            current_date += datetime.timedelta(days=1)
            continue
            
        date_str = format_date(current_date)
        if holidays.find_one({"date": date_str}):
            current_date += datetime.timedelta(days=1)
            continue
        
        # Create absence record
        records.append({
            "employee_id": emp_id,
            "date": date_str,
            "status": "absent",
            "reason": reason
        })
        days_processed += 1
        current_date += datetime.timedelta(days=1)
    
    # Insert records
    if records:
        try:
            attendance.insert_many(records, ordered=False)
        except Exception as e:
            logger.error(f"Error inserting multiday absence: {e}")
            days_processed = f"~{days_processed} (some may have been recorded)"
    
    await update.message.reply_text(
        f"✅ Marked {days_processed} days absence for employee #{simple_id} "
        f"from {format_date_short(start_date)} to {format_date_short(end_date)}"
    )

# --- Main Function ---
def main() -> None:
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Create Telegram application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add_employee", add_employee))
    application.add_handler(CommandHandler("list_employees", list_employees))
    application.add_handler(CommandHandler("remove_employee", remove_employee))
    
    # Report commands
    application.add_handler(CommandHandler("daily_report", daily_report))
    application.add_handler(CommandHandler("date_report", date_report))
    application.add_handler(CommandHandler("last_7_days", last_7_days_report))
    application.add_handler(CommandHandler("last_30_days", last_30_days_report))
    application.add_handler(CommandHandler("monthly_report", monthly_report))
    application.add_handler(CommandHandler("employee_report", employee_report))
    
    # Holiday commands
    application.add_handler(CommandHandler("mark_holiday", mark_holiday))
    application.add_handler(CommandHandler("list_holidays", list_holidays))
    application.add_handler(CommandHandler("remove_holiday", remove_holiday))
    
    # Other commands
    application.add_handler(CommandHandler("multiday_absence", multiday_absence))
    
    # Attendance conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('mark_attendance', mark_attendance)],
        states={
            MARKING_ATTENDANCE: [
                CallbackQueryHandler(handle_attendance_choice, pattern=r'^(present|absent)_\d+$')
            ],
            GETTING_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reason)
            ]
        },
        fallbacks=[],
        allow_reentry=True
    )
    application.add_handler(conv_handler)
    
    # Start the bot with restart logic
    max_retries = 5
    retry_delay = 10  # seconds
    
    while max_retries > 0:
        try:
            logger.info("Starting bot polling...")
            application.run_polling()
            break  # Exit loop if polling stops cleanly
        except Conflict as e:
            logger.error(f"Conflict detected: {e}")
            logger.info(f"Retrying in {retry_delay} seconds... ({max_retries} retries left)")
            max_retries -= 1
            time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.info("Restarting bot...")
            time.sleep(retry_delay)
    
    if max_retries <= 0:
        logger.error("Max retries exceeded. Bot stopped.")

if __name__ == '__main__':
    main()
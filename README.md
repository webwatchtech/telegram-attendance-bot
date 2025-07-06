# Telegram Employee Attendance Bot - Comprehensive Project Documentation

## 📄 Table of Contents
1. [Project Overview](#-project-overview)
2. [System Architecture](#-system-architecture)
3. [Configuration Guide](#-configuration-guide)
4. [Deployment Instructions](#-deployment-instructions)
5. [Command Reference](#-command-reference)
6. [Database Structure](#-database-structure)
7. [Workflow Documentation](#-workflow-documentation)
8. [Backup & Recovery](#-backup--recovery)
9. [Troubleshooting Guide](#-troubleshooting-guide)
10. [Future Enhancements](#-future-enhancements)

## 🌟 Project Overview
The Telegram Employee Attendance Bot is a complete solution for small businesses to track staff attendance with minimal setup.

**Key Benefits**:
- ✅ 100% mobile-friendly via Telegram
- ⚡ Daily attendance in under 60 seconds
- ☁️ Cloud-based storage (MongoDB Atlas)
- 📊 Automatic reporting and analytics
- 🆓 Free to host and operate

**Technical Specifications**:
- **Language**: Python 3.10
- **Framework**: python-telegram-bot v20
- **Database**: MongoDB
- **Hosting**: Free-tier compatible services

## 🏗 System Architecture
```mermaid
graph TD
    A[Telegram App] --> B[Cloud Host]
    B --> C[MongoDB Atlas]
    C --> D[(Database)]
    B --> E[Reporting Engine]
    F[Admin] --> A
```

**Components**:
1. **Telegram Interface**: Handles all user interactions
2. **Command Processor**: Executes business logic
3. **MongoDB Database**: Stores all persistent data
4. **Reporting Engine**: Generates analytics and reports
5. **Cloud Host**: Runs the bot 24/7

## 🔧 Configuration Guide

### Environment Variables
Create `.env` file with:
```ini
# Required variables
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_user_id
MONGODB_URI=mongodb+srv://user:pass@cluster.example.mongodb.net/dbname?retryWrites=true&w=majority

# Optional variables
TIMEZONE=Asia/Kolkata
REPORT_TIME=09:00
```

### MongoDB Setup
1. Create free cluster at [MongoDB Atlas](https://www.mongodb.com/atlas/database)
2. Create database user with read/write privileges
3. Whitelist IP `0.0.0.0` (temporary during setup)
4. Get connection string and add to `.env`

### Bot Setup
1. Create bot with [@BotFather](https://t.me/BotFather):
   ```
   /newbot → Choose name → Get token
   ```
2. Get your user ID with [@userinfobot](https://t.me/userinfobot)
3. Set commands via @BotFather:
   ```
   /setcommands
   start - Start bot
   help - Show help
   add_employee - Add staff
   ... [full command list]
   ```

## 🚀 Deployment Instructions

### Free Hosting Options
1. **Railway.app** (Recommended):
   - Connect GitHub repository
   - Set environment variables
   - Deploy as web service

2. **PythonAnywhere**:
   - Create "Always-On Task"
   - Upload files manually
   - Install dependencies in bash console

3. **Replit + UptimeRobot**:
   - Create Python repl
   - Add environment secrets
   - Set up UptimeRobot to ping every 5 mins

### Deployment Checklist
- [ ] Environment variables configured
- [ ] MongoDB connection verified
- [ ] Bot token added
- [ ] Admin ID set
- [ ] Command menu configured via @BotFather

## 📋 Command Reference

### Employee Management
| Command | Parameters | Example | Description |
|---------|------------|---------|-------------|
| `/add_employee` | `[Name]` | `/add_employee John Doe` | Add new staff member |
| `/list_employees` | - | `/list_employees` | Show active team |
| `/remove_employee` | `[ID]` | `/remove_employee 3` | Deactivate staff |

### Attendance Tracking
| Command | Parameters | Example | Description |
|---------|------------|---------|-------------|
| `/mark_attendance` | - | `/mark_attendance` | Start daily tracking |
| `/multiday_absence` | `[ID] [Start] [End] [Reason]` | `/multiday_absence 2 15-07-2025 18-07-2025 "Vacation"` | Batch absence marking |

### Reporting
| Command | Parameters | Example | Description |
|---------|------------|---------|-------------|
| `/daily_report` | - | `/daily_report` | Today's summary |
| `/date_report` | `[DD-MM-YYYY]` | `/date_report 15-07-2025` | Specific date report |
| `/last_7_days` | - | `/last_7_days` | Weekly summary |
| `/last_30_days` | - | `/last_30_days` | Last 30 days summary |
| `/monthly_report` | - | `/monthly_report` | Calendar month report |
| `/employee_report` | `[ID]` | `/employee_report 2` | Individual performance |

### Holiday Management
| Command | Parameters | Example | Description |
|---------|------------|---------|-------------|
| `/mark_holiday` | - | `[Description]` | Mark holiday |
| `/list_holidays` | - | - | View all holidays |
| `/remove_holiday` | - | `[DD-MM-YYYY]` | Delete holiday |

## 🗄 Database Structure

### Collections
1. **employees**:
   ```javascript
   {
     _id: ObjectId,
     name: String,
     active: Boolean
   }
   ```

2. **attendance**:
   ```javascript
   {
     _id: ObjectId,
     employee_id: ObjectId,
     date: String,  // DD-MM-YYYY format
     status: String, // 'present' or 'absent'
     reason: String
   }
   ```

3. **holidays**:
   ```javascript
   {
     _id: ObjectId,
     date: String,  // DD-MM-YYYY format
     description: String
   }
   ```

### Indexes
```javascript
db.employees.createIndex({"name": 1})
db.attendance.createIndex(
  {"employee_id": 1, "date": 1}, 
  {unique: true}
)
db.holidays.createIndex({"date": 1}, {unique: true})
```

## 🔄 Workflow Documentation

### Daily Attendance Flow
```mermaid
sequenceDiagram
    participant Admin
    participant Bot
    participant DB
    Admin->>Bot: /mark_attendance
    Bot->>DB: Get active employees
    DB-->>Bot: Employee list
    loop For each employee
        Bot->>Admin: Show employee
        Admin->>Bot: ✅ Present / ❌ Absent
        alt Absent selected
            Bot->>Admin: "Reason?"
            Admin->>Bot: Reason text
        end
    end
    Bot->>DB: Save records
    Bot->>Admin: "Attendance complete!"
```

### Report Generation
```mermaid
graph TD
    A[Command] --> B{Report Type}
    B -->|Daily| C[Get today's records]
    B -->|Date| D[Get specific date]
    B -->|Period| E[Calculate date range]
    C --> F[Process data]
    D --> F
    E --> F
    F --> G[Generate summary]
    G --> H[Format output]
    H --> I[Send to admin]
```

## 💾 Backup & Recovery

### MongoDB Backup
1. Manual Export:
   ```bash
   mongodump --uri="mongodb+srv://user:pass@cluster.example.net/dbname" --out=./backup
   ```
2. Automate with Atlas:
   - Enable scheduled snapshots
   - Set retention policy (7 days free)

### Bot Configuration Backup
1. Save `.env` file securely
2. Export command list from @BotFather
3. Save this documentation file

### Full Recovery Process
1. Create new bot with @BotFather (same token if possible)
2. Set up MongoDB (new or restore backup)
3. Deploy code to cloud provider
4. Configure environment variables
5. Test with `/start` command

## 🛠 Troubleshooting Guide

### Common Issues
| Symptom | Solution |
|---------|----------|
| Bot not responding | Check cloud provider logs |
| "Missing variables" error | Verify .env file or environment variables |
| "Employee not found" | Use /list_employees to verify IDs |
| Can't mark attendance on Sunday | This is intentional - not an error |
| Report not generating | Wait 10 seconds and try again |

### Error Messages
- **"Unauthorized access"**: ADMIN_ID doesn't match current user
- **"Invalid date format"**: Use DD-MM-YYYY format
- **"Start date must be before end date"**: Correct date order
- **"Today is a holiday"**: Normal behavior, not an error

## 🚀 Future Enhancements

### Planned Features
1. **Employee Self-Service Portal**:
   - Web interface for employees to view their attendance
   - Leave request submission
   
2. **Automated Reminders**:
   - Daily attendance prompts
   - Monthly report auto-delivery
   
3. **Payroll Integration**:
   - Salary calculation based on attendance
   - Export to accounting software
   
4. **Advanced Analytics**:
   - Yearly trends
   - Department-wise comparisons
   - Overtime tracking

### Technical Improvements
1. Shift to webhooks for better scalability
2. Add multi-admin support
3. Implement Redis caching for faster reports
4. Containerize with Docker for easier deployment

---

**Maintenance Tip**: Regularly update dependencies using:
```bash
pip install -U -r requirements.txt
```

**Critical Note**: Always keep a copy of this documentation separate from your code repository to ensure you can rebuild the project if you lose access to your GitHub account.

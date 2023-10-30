# -*- coding: utf-8 -*-
# Copyright (c) 2023, libracore and contributors
# For license information, please see license.txt
#
# from heimbohrtechnik.heim_bohrtechnik.email_handler import save_message

from email.message import EmailMessage
from email.policy import SMTP
from email.mime.text import MIMEText
import mimetypes
from frappe.desk.form.load import get_attachments
from os import path, remove
from heimbohrtechnik.heim_bohrtechnik.nextcloud import get_physical_path, get_path, write_project_file_from_local_file
import frappe
import html2text
import time
import json
from frappe.utils import cint

# this function will take a communication and store it as a local file
#
# params: communication ID and target file path
def save_message(communication, target_file, debug=False):
    doc = frappe.get_doc("Communication", communication)
    
    # create base message
    msg = EmailMessage()
    msg['Subject'] = (doc.subject or "").replace("\n", "").replace("\r", "")
    msg['From'] = doc.sender
    if doc.get("recipients"):
        msg['To'] = cleanup_email_str(doc.recipients)
    if doc.get("cc"):
        msg['Cc'] = cleanup_email_str(doc.cc)
    if doc.get("bcc"):
        msg['Bcc'] = cleanup_email_str(doc.bcc)
    msg['Date'] = doc.communication_date
    msg.set_content(html2text.html2text(doc.content))
    msg.add_alternative(doc.content, subtype='html')
    # add attachments
    email_queue = frappe.db.sql("""
        SELECT `attachments` 
        FROM `tabEmail Queue` 
        WHERE `communication` = "{communication}";""".format(communication=communication), as_dict=True)
        
    if len(email_queue) > 0:
        attachments = json.loads(email_queue[0].get("attachments"))
        if debug:
            print("{0}".format(attachments))
        for a in attachments:
            if cint(a.get("print_format_attachment")) == 1:
                # document print
                pdf = frappe.get_print(
                    doctype=a.get("doctype"), 
                    name=a.get("name"), 
                    print_format=a.get("print_format"), 
                    as_pdf=True
                )
                file_name = "{0}.pdf".format(a.get("name"))
                ctype = "application/pdf"
                maintype, subtype = ctype.split("/", 1)
                try:
                    msg.add_attachment(pdf, maintype=maintype, subtype=subtype, filename=file_name)
                except Exception as err:
                    print("{0}: {1}".format(file_name, err))    # skip file if it cannot be read
            else:
                # normal document attached 
                full_name = get_physical_path(a.get("fid"))
                file_name = frappe.get_value("File", a.get("fid"), "file_name")
                ctype, encoding = mimetypes.guess_type(full_name)
                if ctype is None or encoding is not None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)
                try:
                    with open(full_name, 'rb') as fp:
                        msg.add_attachment(fp.read(), maintype=maintype, subtype=subtype, filename=file_name)
                except Exception as err:
                    print("{0}: {1}".format(file_name, err))    # skip file if it cannot be read
    else:
        print("Has no attachments")
        
    # store
    with open(target_file, 'wb') as fp:
        fp.write(msg.as_bytes(policy=SMTP))
        
    return

"""
This function will delay sending by 30 seconds to allow for file uploads to complete
"""
def delayed_upload_communication_to_nextcloud(communication):
    time.sleep(30)          # wait 30 seconds
    upload_communication_to_nextcloud(communication)
    return
    
def upload_communication_to_nextcloud(communication):
    # create file
    communication = frappe.get_doc("Communication", communication)
    tmp_file = "/tmp/" + ("{0}_{1}.eml".format(communication.subject, communication.name)).replace("/", "_").replace(":", "_")
    save_message(communication.name, tmp_file)
    
    # select target
    project = None
    
    if communication.reference_doctype == "Project":
        project = communication.reference_name
        if "Bohrstart" in communication.subject:
            target = get_path('drilling')
        elif "Fertigstellung" in communication.subject:
            target = get_path('drilling')
        elif "Saugwagenbestellung" in communication.subject or "Muldenbestellung" in communication.subject:
            target = get_path('supplier_mud')
        else:
            target = get_path('drilling')
    elif communication.reference_doctype == "Sales Invoice":
        project = frappe.get_value("Sales Invoice", communication.reference_name, "object")
        target = get_path('invoice')
    elif communication.reference_doctype == "Bohranzeige":
        project = frappe.get_value("Bohranzeige", communication.reference_name, "project")
        target = get_path('drilling')
    elif communication.reference_doctype == "Request for Public Area Use":
        project = frappe.get_value("Request for Public Area Use", communication.reference_name, "project")
        target = get_path('road')
    elif communication.reference_doctype == "Sales Order":
        project = frappe.get_value("Sales Order", communication.reference_name, "object")
        target = get_path('order')
    elif communication.reference_doctype == "Purchase Order":
        project = frappe.get_value("Purchase Order", communication.reference_name, "object")
        target = get_path('supplier_ews')
        
    # upload to nextcloud
    if project:
        write_project_file_from_local_file(project, tmp_file, target)
    else:
        print("No project found")
        
    # clear file
    remove(tmp_file)
    
    return

"""
Hook from Communication: create file and upload to nextcloud
"""
def communication_on_insert(self, event):
    try:
        delayed_upload_communication_to_nextcloud(self.name)
    except Exception as err:
        if not "/P-MX-" in err:         # exclude upload errors from MudEX documents where there is no project folder
            frappe.log_error(err, "Communication hook failed")
    return
    
def cleanup_email_str(email_str):
    s = (email_str or "").strip()
    if s.endswith(","):
        s = s[:-1]
    return s
    

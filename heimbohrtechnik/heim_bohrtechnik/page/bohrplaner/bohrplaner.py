# -*- coding: utf-8 -*-
# Copyright (c) 2017-2023, libracore and contributors

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils.data import getdate, date_diff, add_days, get_datetime
from datetime import date, timedelta
from frappe.desk.form.load import get_attachments
from frappe.utils import cint, get_url_to_form

BG_GREEN = '#81d41a;'
BG_ORANGE = '#ffbf00;'
BG_RED = '#ffa6a6;'
BG_LIGHT_GREEN = '#eefdec;'
BG_DARK_GREEN = '#006400;'
BG_GREY = '#c4c7ca;'
BG_BLUE = '#9dc7f0;'
BG_WHITE = '#ffffff;'
BG_BLACK = '#000000;'

WEEKDAYS = {
    0: "So",
    1: "Mo", 
    2: "Di",
    3: "Mi",
    4: "Do",
    5: "Fr",
    6: "Sa"
}
@frappe.whitelist()
def get_overlay_datas(from_date, to_date, customer=None):
    projects = []
    
    customer_filter = ""
    if customer:
        customer_filter =  """ AND `tabProject`.`customer` = "{customer}" """.format(customer=customer)
        
    matching_projects = frappe.db.sql("""
        SELECT 
            `name`, 
            `drilling_team`, 
            `expected_start_date`, 
            `expected_end_date`, 
            `start_half_day`, 
            `end_half_day`, 
            `object`
        FROM `tabProject`
        WHERE `project_type` = "External"
          AND `status` IN ("Open", "Completed")
          AND 
            ((`expected_start_date` BETWEEN '{from_date}' AND '{to_date}')
             OR (`expected_end_date` BETWEEN '{from_date}' AND '{to_date}')
             OR (`expected_start_date` < '{from_date}' AND `expected_end_date` > '{to_date}')
            )
          {customer_filter}
        """.format(from_date=from_date, to_date=to_date, customer_filter=customer_filter), as_dict=True)

    for p in matching_projects:
        if p.expected_start_date < getdate(from_date):
            p.expected_start_date = getdate(from_date)
            if p.start_half_day.lower() == 'nm':
                p.start_half_day = 'vm'
        
        dauer = calc_duration(p.expected_start_date, p.expected_end_date, from_date, to_date)['dauer']
        if p.start_half_day.lower() == 'nm' :
            dauer -= 1
        if p.end_half_day.lower() == 'vm' and (p.expected_end_date.weekday() < 5 and p.expected_end_date <= getdate(to_date)):
            dauer -= 1
        
        p_data = get_project_data(p, dauer)
        projects.append(p_data)
        
    return projects
    
def get_project_data(p, dauer):
    project = frappe.get_doc("Project", p.name)
    p_object = frappe.get_doc("Object", p.object)
    construction_sites = frappe.get_all("Construction Site Description", 
        filters={'project': p.name}, 
        fields=['name', 'internal_crane_required', 'external_crane_Required', 'carrymax'])
    manager_short = frappe.get_cached_value("User", project.manager, "username") if project.manager else ''
    drilling_equipment = []
    if len(construction_sites) > 0:
        construction_site = frappe.get_doc("Construction Site Description", construction_sites[0].get('name'))
        for de in (construction_site.drilling_equipment or []):
            drilling_equipment.append(de.drilling_equipment)
        drilling_equipment = ", ".join(drilling_equipment)
    if drilling_equipment == []:            # no construction site description, rewrite to empty string
        drilling_equipment = ""
    saugauftrag = 'Schlamm fremd'
    mud = None
    mud_supplier = None
    pneukran = ''
    pneukran_details = {}
    activities = {
        'internal_crane': frappe.get_cached_value("Heim Settings", "Heim Settings", "int_crane_activity"),
        'external_crane': frappe.get_cached_value("Heim Settings", "Heim Settings", "crane_activity"),
        'carrymax': frappe.get_cached_value("Heim Settings", "Heim Settings", "carrymax_activity"),
        'mud': frappe.get_cached_value("Heim Settings", "Heim Settings", "mud_disposer_activity"),
        'trough': frappe.get_cached_value("Heim Settings", "Heim Settings", "trough_activity"),
    }
    flag_ext_crane = False
    flag_int_crane = False
    flag_carrymax = False
    flag_override_mud = False
    # read project checklist
    for cl_entry in project.checklist:
        if cl_entry.activity == activities['mud']:
            saugauftrag = cl_entry.supplier_short_display or cl_entry.supplier_name
            if cl_entry.supplier == "L-03749":
                flag_override_mud = True
        elif cl_entry.activity == activities['external_crane']:
            pneukran_details = cl_entry.as_dict()
            flag_ext_crane = True
        elif cl_entry.activity == activities['internal_crane']:
            pneukran_details = cl_entry.as_dict()
            flag_int_crane = True
        elif cl_entry.activity == activities['trough']:
            mud = cl_entry.supplier_short_display or cl_entry.supplier_name
        elif cl_entry.activity == activities['carrymax']:
            flag_carrymax = True
    
    # read construction site
    if len(construction_sites) > 0:
        if construction_sites[0].get('carrymax') == 1:
            flag_carrymax = True
        elif construction_sites[0].get('internal_crane_required') == 1:
            flag_int_crane = True
        elif construction_sites[0].get('external_crane_required') == 1:
            flag_ext_crane = True
            
    # set crane base
    if flag_ext_crane:
        pneukran = pneukran_details.get('supplier_short_display') or pneukran_details.get('supplier_name') or "ext. Kran"
    if flag_int_crane:
        pneukran = pneukran_details.get('supplier_short_display') or pneukran_details.get('supplier_name') or "int. Kran"
    if flag_ext_crane and flag_int_crane:
        # conflict
        pneukran = "(!)" + pneukran
    if flag_carrymax:
        if pneukran:
            pneukran += ", Carrymax"
        else:
            pneukran = "Carrymax"
            
    # extend crane details
    if 'appointment' in pneukran_details and pneukran_details['appointment']:
        
        pneukran += ", {0}".format(get_short_time(pneukran_details['appointment']))
    if 'appointment_end' in pneukran_details and pneukran_details['appointment_end']:
        pneukran += " / {0}".format(get_short_time(pneukran_details['appointment_end']))
        
    # override mud for special case
    if flag_override_mud:
        saugauftrag = mud
        
    p_data = {
            'bohrteam': p.drilling_team,
            'start': get_datetime(p.expected_start_date).strftime('%d.%m.%Y'),
            'vmnm': p.start_half_day.lower(),
            'dauer': dauer,
            'ampeln': get_traffic_lights_indicator(project),
            'project': project,
            'saugauftrag': saugauftrag,
            'pneukran': pneukran,
            'manager_short': manager_short,
            'drilling_equipment': drilling_equipment
        }
        
    return p_data

def get_short_time(d):
    day = WEEKDAYS[cint(d.strftime("%w"))]
    s = "{0} {1}".format(day, d.strftime("%H:%M"))
    return s
    
@frappe.whitelist()
def get_internal_overlay_datas(from_date, to_date):
    projects = []
    
    matching_projects = frappe.db.sql("""
                                            SELECT 
                                                `name`, 
                                                `drilling_team`, 
                                                `expected_start_date`, 
                                                `expected_end_date`, 
                                                `start_half_day`, 
                                                `end_half_day`, 
                                                `object`
                                            FROM `tabProject`
                                            WHERE `project_type` = "Internal"
                                              AND 
                                                ((`expected_start_date` BETWEEN '{from_date}' AND '{to_date}')
                                                 OR (`expected_end_date` BETWEEN '{from_date}' AND '{to_date}')
                                                 OR (`expected_start_date` < '{from_date}' AND `expected_end_date` > '{to_date}')
                                                )""".format(from_date=from_date, to_date=to_date), as_dict=True)
    for p in matching_projects:
        project = frappe.get_doc("Project", p.name)
        if p.expected_start_date < getdate(from_date):
            p.expected_start_date = getdate(from_date)
            if p.start_half_day.lower() == 'nm':
                p.start_half_day = 'vm'
        
        dauer = calc_duration(p.expected_start_date, p.expected_end_date, from_date, to_date)['dauer']
        if p.start_half_day.lower() == 'nm' :
            dauer -= 1
        if p.end_half_day.lower() == 'vm' and (p.expected_end_date.weekday() < 5 and p.expected_end_date <= getdate(to_date)):
            dauer -= 1
        
        p_data = {
            'bohrteam': p.drilling_team,
            'start': get_datetime(p.expected_start_date).strftime('%d.%m.%Y'),
            'vmnm': p.start_half_day.lower(),
            'dauer': dauer,
            'project': project
        }
        projects.append(p_data)
    
    return projects
    
@frappe.whitelist()
def get_subproject_overlay_datas(from_date, to_date):
    subproject_list = []
    shift_controll = {}
    subprojects = frappe.db.sql("""
        SELECT
            `tabProject Subproject`.`start`,
            `tabProject Subproject`.`end`,
            `tabProject Subproject`.`team`,
            `tabProject Subproject`.`description`,
            `tabProject Subproject`.`subcontracting_order` AS `subcontracting_order`,
            `tabProject`.`name` as `project`,
            `tabProject`.`customer_name` as `customer_name`,
            `tabProject`.`ews_details` as `ews_details`,
            `tabProject`.`object_name`,
            `tabProject`.`object_street`,
            `tabProject`.`object_location`
        FROM `tabProject Subproject`
        LEFT JOIN `tabProject` ON `tabProject`.`name` = `tabProject Subproject`.`parent`
        LEFT JOIN `tabSubcontracting Order` ON `tabSubcontracting Order`.`name` = `tabProject Subproject`.`subcontracting_order`
        WHERE 
            (`tabProject Subproject`.`start` BETWEEN "{from_date}" AND "{to_date}"
            OR `tabProject Subproject`.`end` BETWEEN "{from_date}" AND "{to_date}")
            AND `tabProject`.`status` IN ("Open", "Completed")
        ORDER BY 
            `tabProject Subproject`.`team` ASC, `tabSubcontracting Order`.`prio` ASC;""".format(
            from_date=from_date, to_date=to_date), as_dict=True)
    for subproject in subprojects:
        subproject_duration = calc_duration(subproject.start, subproject.end, from_date, to_date)
        subproject_shift, shift_controll = subproject_shift_controll(subproject, get_datetime(subproject_duration['start']).strftime('%d.%m.%Y'), shift_controll)
        
        subproject_data = {
            'bohrteam': subproject.team,
            'start': get_datetime(subproject_duration['start']).strftime('%d.%m.%Y'),
            'dauer': subproject_duration['dauer'],
            'description': subproject.description,
            'id': subproject.name,
            'subproject_shift': subproject_shift,
            'project': subproject.project,
            'customer_name': subproject.customer_name,
            'ews_details': subproject.ews_details,
            'object_name': subproject.object_name,
            'object_street': subproject.object_street,
            'object_location': subproject.object_location,
            'subcontracting_order': subproject.subcontracting_order
        }
        subproject_list.append(subproject_data)
    
    return subproject_list

def calc_duration(start, end, from_date, to_date):
    '''
    start = record start date
    end = record end date
    from_date = filter from date
    to_date = filter to date
    start_date = latest (record or filter) start/from date
    end_date = earliest (record or filter) end/to date
    '''
    if start < getdate(from_date):
        start_date = getdate(from_date)
    else:
        start_date = start
    if end > getdate(to_date):
        end_date = getdate(to_date)
    else:
        end_date = end
    
    fixed_start = start_date
    delta = timedelta(days=1)
    duration = 0
    while start_date <= end_date:
        week_day_no = start_date.weekday()
        if week_day_no < 5:
            duration += 2
        else:
            duration += 0.5
        start_date += delta
    
    return {
        'dauer': duration,
        'start': fixed_start
    }
    

def subproject_shift_controll(subproject, start, shift_controll):
    if str(start) + str(subproject.team) in shift_controll:
        shift_controll[str(start) + str(subproject.team)] += 1
        return shift_controll[str(start) + str(subproject.team)], shift_controll
    else:
        shift_controll[str(start) + str(subproject.team)] = 0
        return 0, shift_controll

def get_traffic_lights_indicator(project):
    colors = []
    
    # projeknummer [0]
    projeknummer_color = BG_RED                     # red
    if cint(project.termin_bestaetigt) == 1:
        projeknummer_color = BG_ORANGE              # orange
    if project.sales_order:
        akonto = int(frappe.db.sql("""
            SELECT COUNT(`tabSales Invoice`.`name`) AS `qty` 
            FROM `tabSales Invoice Item`
            LEFT JOIN `tabSales Invoice` ON `tabSales Invoice`.`name` = `tabSales Invoice Item`.`parent`
            WHERE `tabSales Invoice Item`.`sales_order` = '{so}' 
              AND `tabSales Invoice`.`docstatus` = 1
              AND `tabSales Invoice`.`title` = "Teilrechnung"; """.format(so=project.sales_order), as_dict=True)[0].qty)
        if akonto > 0:
            projeknummer_color = BG_LIGHT_GREEN         # light green
        sinv = int(frappe.db.sql("""
            SELECT COUNT(`tabSales Invoice`.`name`) AS `qty` 
            FROM `tabSales Invoice Item` 
            LEFT JOIN `tabSales Invoice` ON `tabSales Invoice`.`name` = `tabSales Invoice Item`.`parent`
            WHERE `tabSales Invoice Item`.`parenttype` = 'Sales Invoice' 
              AND `tabSales Invoice Item`.`sales_order` = '{so}' 
              AND `tabSales Invoice`.`docstatus` = 1 
              AND `tabSales Invoice`.`title` IN ("Schlussrechnung", "Rechnung"); 
            """.format(so=project.sales_order), as_dict=True)[0].qty)
        if sinv > 0:
            projeknummer_color = BG_GREEN           # green
    colors.append(projeknummer_color)
    
    # auftraggeber [1]
    auftraggeber_color = BG_RED                     # red
    if project.sales_order:
        unterzeichnete_ab = frappe.get_value("Sales Order", project.sales_order, "unterzeichnete_ab")
        if unterzeichnete_ab:
            auftraggeber_color = BG_GREEN           # green: signed sales order file
    colors.append(auftraggeber_color)
    
    # objektname [2]
    objektname_color = BG_RED                       # base: red
    found_permits = 0
    found_permits_with_file = 0
    if not project.permits or len(project.permits) == 0:
        objektname_color = BG_GREY                  # project has not permit records: grey
    else:
        for permit in project.permits:
            if 'Bohrbewilligung kantonal' in permit.permit:
                found_permits += 1
                if permit.file:
                    found_permits_with_file += 1
        if found_permits > 0 and found_permits == found_permits_with_file:
            objektname_color = BG_GREEN         # all permits available: green
    colors.append(objektname_color)
    
    # objekt_strasse [3]
    objekt_strasse_color = BG_GREY              # start with grey
    drill_notices = frappe.get_all("Bohranzeige", filters={'project': project.name}, fields={'name'})
    if len(drill_notices) > 0:
        # has a drill notice: red
        objekt_strasse_color = BG_RED           # red
    if cint(project.drill_notice_sent) == 1:
        objekt_strasse_color = BG_GREEN         # green
    colors.append(objekt_strasse_color)
    
    # objekt_plz_ort [4, 5, 6]
    objekt_plz_ort_color = BG_GREY              # grey
    if int(project.thermozement) == 1:
        objekt_plz_ort_color = BG_BLUE          # blue
    colors.append(objekt_plz_ort_color)         # 4
    objekt_plz_ort_font_color = BG_BLACK
    objekt_plz_ort_border_color = ''
    for permit in project.permits:
        if 'Lärmschutzbewilligung' in permit.permit:
            objekt_plz_ort_font_color = BG_RED
            if project.noise_permit_requested:
                objekt_plz_ort_font_color = BG_ORANGE
            if permit.file:
                objekt_plz_ort_font_color = BG_DARK_GREEN            # dark green
        #elif 'Strassensperrung' in permit.permit:              # removed by change request RB/2022-10-05
        #    if not permit.file:
        #        objekt_plz_ort_border_color = 'border: 1px solid red;'
    colors.append(objekt_plz_ort_font_color)       # 5
    colors.append(objekt_plz_ort_border_color)     # 6
    
    #ews_details [7]
    ews_details_color = BG_RED                      # red
    po = frappe.db.sql("""SELECT `per_received` FROM `tabPurchase Order` WHERE `object` = '{0}' AND `docstatus` = 1""".format(project.object), as_dict=True)
    if len(po) > 0:
        ews_details_color = BG_ORANGE               # yellow: ordered
        if cint(po[0].per_received) == 100:
            ews_details_color = BG_GREEN            # green: available
    colors.append(ews_details_color)
    
    # saugauftrag [8]
    saugauftrag_color = BG_GREY                     # grey
    for cl_entry in project.checklist:
        if cl_entry.activity == 'Schlammentsorgung':
            saugauftrag_color = BG_ORANGE           # orange
            #if cl_entry.supplier_name:
            if project.trough_ordered:
                saugauftrag_color = BG_GREEN        # green
    colors.append(saugauftrag_color)
    
    # pneukran [9]
    pneukran_color = BG_GREY                        # grey
    if cint(project.crane_required) == 1:
        if cint(project.crane_organized) == 1:
            pneukran_color = BG_GREEN               # green
        else:
            pneukran_color = BG_ORANGE              # orange
    colors.append(pneukran_color)
    
    # typ_bohrgeraet [10] - find infomail and file
    typ_bohrgeraet_color = BG_RED                   # start with red
    if has_infomail(project.name):
        typ_bohrgeraet_color = BG_ORANGE            # has infomail: orange
        if project.project_file_created:
            typ_bohrgeraet_color = BG_GREEN         # project file has been created
    colors.append(typ_bohrgeraet_color)
    
    # kuerzel_pl [11]
    kuerzel_pl_color = BG_RED                       # red
    if is_construction_site_inspected(project.name) == 1:
        kuerzel_pl_color = BG_GREEN                 # green
    elif project.visit_date:
        kuerzel_pl_color = BG_ORANGE                # orange
    colors.append(kuerzel_pl_color)
    
    # strassensperrung [12]
    strassensperrung_color = BG_GREY                    # grey: not applicable
    for permit in project.permits:
        if 'Strassensperrung' in permit.permit:
            #strassensperrung_color = BG_RED            # red: not used - should always be in the list
            if has_public_area_request(project.name):
                strassensperrung_color = BG_ORANGE      # orange: requested
            if permit.file:                         
                strassensperrung_color = BG_GREEN       # green: permit available
    colors.append(strassensperrung_color)
    
    # drill order [13]
    kuerzel_pl_font_color = BG_BLACK
    if cint(project.drill_order_created) == 1:
        kuerzel_pl_font_color = BG_WHITE              # white
    colors.append(kuerzel_pl_font_color)
    return colors

def is_construction_site_inspected(project):
    inspected = frappe.db.sql("""
        SELECT MAX(`tabConstruction Site Description`.`site_inspected`) AS `is_inspected`
        FROM `tabConstruction Site Description`
        WHERE `tabConstruction Site Description`.`project` = "{project}";
    """.format(project=project), as_dict=True)
    return inspected[0]['is_inspected'] if len(inspected) > 0 else 0
    
def has_public_area_request(project):
    public_area_requests = frappe.db.sql("""
        SELECT 
            `tabRequest for Public Area Use`.`name`,
            `tabRequest for Public Area Use`.`sent` 
        FROM `tabRequest for Public Area Use` 
        LEFT JOIN `tabRelated Project` ON `tabRelated Project`.`parent` = `tabRequest for Public Area Use`.`name` 
        WHERE 
            `tabRequest for Public Area Use`.`project` = "{project}" 
            OR (`tabRelated Project`.`parenttype` = "Request for Public Area Use"  
                AND `tabRelated Project`.`project` = "{project}");
        """.format(project=project), as_dict=True)
        
    if len(public_area_requests) > 0 and public_area_requests[0]['sent'] == 1:
        return True
    else:
        return False

def has_infomail(project):
    infomails = frappe.get_all("Infomail",
        filters={'project': project},
        fields=['name']
    )
    return True if len(infomails) > 0 else False
        
@frappe.whitelist()
def reschedule_project(project=None, team=None, day=None, start_half_day=None, popup=False, 
    new_project_start=None, new_project_end_date=None, end_half_day=None, visit_date=None):
    project = frappe.get_doc("Project", project)
    project.visit_date = visit_date
    
    if not popup:
        start_date = project.expected_start_date
        end_date = project.expected_end_date
        project_duration = date_diff(end_date, start_date)
        delta = timedelta(days=project_duration)
        
        new_project_start_day = day.split(".")[0]
        new_project_start_month = day.split(".")[1]
        new_project_start_year = day.split(".")[2]
        new_project_start = getdate(new_project_start_year + "-" + new_project_start_month + "-" + new_project_start_day)
        
        new_project_end_date = new_project_start
        new_project_end_date += delta
        
        project.expected_start_date = new_project_start
        project.expected_end_date = new_project_end_date
        
        if project.start_half_day != start_half_day.upper():
            old_start_hd = project.start_half_day
            project.start_half_day = start_half_day.upper()
            if old_start_hd == 'NM':
                if project.end_half_day == 'NM':
                    project.end_half_day = 'VM'
                else:
                    project.end_half_day = 'NM'
            else:
                if project.end_half_day == 'VM':
                    project.end_half_day = 'NM'
                else:
                    project.end_half_day = 'VM'
        
        project.drilling_team = team
        project.crane_organized = '0'
        project.save()
    else:
        project.expected_start_date = getdate(new_project_start)
        project.expected_end_date = getdate(new_project_end_date)
        project.start_half_day = start_half_day
        project.end_half_day = end_half_day
        project.drilling_team = team
        project.crane_organized = '0'
        project.save()

@frappe.whitelist()
def reschedule_subcontracting(subcontracting=None, team=None, day=None):
    subcontracting = frappe.get_doc("Subcontracting Order", subcontracting)
    
    start_date = subcontracting.from_date
    end_date = subcontracting.to_date
    subcontracting_duration = date_diff(end_date, start_date)
    delta = timedelta(days=subcontracting_duration)
    
    new_subcontracting_start_day = day.split(".")[0]
    new_subcontracting_start_month = day.split(".")[1]
    new_subcontracting_start_year = day.split(".")[2]
    new_subcontracting_start = getdate(new_subcontracting_start_year + "-" + new_subcontracting_start_month + "-" + new_subcontracting_start_day)
    
    new_subcontracting_end_date = new_subcontracting_start
    new_subcontracting_end_date += delta
    
    subcontracting.from_date = new_subcontracting_start
    subcontracting.to_date = new_subcontracting_end_date
    
    if frappe.db.exists("Drilling Team", team):
        subcontracting.drilling_team = team
    else:
        team = team.replace("-2", "").replace("-3", "")
        if frappe.db.exists("Drilling Team", team):
            subcontracting.drilling_team = team
    subcontracting.save()
    
@frappe.whitelist()
def get_content(from_date, to_date, only_teams=False):
    data = {}
    data["drilling_teams"] = get_drilling_teams(only_teams)
    data["days"], data["weekend"], data["kw_list"], data["day_list"], data["today"] = get_days(from_date, to_date)
    return data
    
def get_days(from_date, to_date):
    start_date = getdate(from_date)
    end_date = getdate(to_date)
    date_list = []
    weekend_list = []
    kw_list = {}
    day_list = {}
    company = frappe.defaults.get_user_default("Company")
    holidaylist = frappe.get_doc("Company", company).default_holiday_list
    if holidaylist:
        holidaylist = frappe.get_doc("Holiday List", holidaylist)
        holidays = []
        for holiday in holidaylist.holidays:
            holidays.append(holiday.holiday_date.strftime("%d.%m.%Y"))
    delta = timedelta(days=1)
    while start_date <= end_date:
        date_list.append(start_date.strftime("%d.%m.%Y"))
        kw_list[start_date.strftime("%d.%m.%Y")] = start_date.strftime("%V")
        day_list[start_date.strftime("%d.%m.%Y")] = start_date.strftime("%a")
        week_day_no = start_date.weekday()
        if holidaylist:
            if start_date.strftime("%d.%m.%Y") in holidays:
                weekend_list.append(start_date.strftime("%d.%m.%Y"))
            start_date += delta
        else:
            if week_day_no >= 5:
                weekend_list.append(start_date.strftime("%d.%m.%Y"))
            start_date += delta
        
    today = date.today()
    today = today.strftime("%d.%m.%Y")
    
    return date_list, weekend_list, kw_list, day_list, today

def get_weekend_day_correction(from_date, to_date):
    start_date = getdate(from_date)
    end_date = getdate(to_date)
    delta = timedelta(days=1)
    sundays = 0
    while start_date <= end_date:
        week_day_no = start_date.weekday()
        if week_day_no == 6:
            sundays += 3
        start_date += delta
    
    return sundays
    
def get_drilling_teams(only_teams=False):
    team_filter = ''
    if only_teams:
        team_filter = """WHERE `drilling_team_type` = 'Bohrteam'"""
    drilling_teams = frappe.db.sql("""
        SELECT 
            `name` AS `team_id`, 
            `title`, 
            `drm`, 
            `drt`, 
            `truck_and_weight`, 
            `has_trough`, 
            IFNULL(`trough_details`, "{trough}") AS `trough_details`, 
            `has_crane`, 
            IFNULL(`crane_details`, "{crane}") AS `crane_details`, 
            `phone`,
            `drilling_team_type`
        FROM `tabDrilling Team`
        {team_filter}""".format(
            trough=_('Has Trough'), crane=_('Has Crane'), team_filter=team_filter), as_dict=True)
        
    return drilling_teams

# Absences
@frappe.whitelist()
def get_absences_overlay_datas(from_date, to_date):
    from_date = getdate(from_date)
    to_date = getdate(to_date)
    absences = []
    shift = 0
    last_date = None
    
    absences_raw = frappe.db.sql("""
        SELECT
            `name`,
            `employee`,
            `employee_name`,
            `from_date`,
            `to_date`
        FROM `tabLeave Application`
        WHERE 
            (`from_date` BETWEEN '{from_date}' AND '{to_date}')
        OR
            (`to_date` BETWEEN '{from_date}' AND '{to_date}')
        OR
            (`from_date` < '{from_date}' AND `to_date` > '{to_date}')
        ORDER BY `from_date` ASC, `employee_name` ASC;""".format(from_date=from_date, to_date=to_date), as_dict=True)
    
    for absence in absences_raw:
        duration = calc_duration(absence.from_date, absence.to_date, from_date, to_date)     # in ['dauer'] segments
        if not last_date or absence.from_date > last_date:
            shift = 0
        else:
            shift += 20
        if not last_date or absence.to_date > last_date:
            # add max. 2 weeks threshold to prevent stacking on long absences (military, ...)
            if last_date and duration['dauer'] > 22:                    # 22 segments = typically 2 weeks
                last_date = last_date + timedelta(days=14)
            else:
                last_date = absence.to_date
            
        _absence = {
            'start': get_datetime(duration['start']).strftime('%d.%m.%Y'),
            'dauer': duration['dauer'],
            'employee_name': absence.employee_name,
            'absence': absence.name,
            'shift': shift
        }
        absences.append(_absence)
    
    return absences

@frappe.whitelist()
def get_user_planning_days(user):
    if frappe.db.exists("Signature", user):
        return {
            'planning_days': frappe.get_value("Signature", user, "planning_days") or 30,
            'planning_past_days': frappe.get_value("Signature", user, "planning_past_days") or 0
        }
    else:
        return {
            'planning_days': 30,
            'planning_past_Days': 0
        }
    
@frappe.whitelist()
def print_bohrplaner(html):
    from frappe.utils.pdf import get_pdf
    from PyPDF2 import PdfFileWriter
    from frappe.utils.pdf import get_file_data_from_writer
    from erpnextswiss.erpnextswiss.attach_pdf import create_folder
    
    bohrplaner_css = frappe.read_file("{0}{1}".format(frappe.utils.get_bench_path(), "/apps/heimbohrtechnik/heimbohrtechnik/heim_bohrtechnik/page/bohrplaner/bohrplaner.css"))

    html = html + """<body>
        <meta name="pdfkit-orientation" content="Portrait"/><style>
        .print-format {
         margin-top: 0mm;
         margin-left: 0mm;
         margin-right: 0mm;
        }
        
        .object-div {
            font-size: 9pt !important;
        }
        """ + bohrplaner_css + "</style></body>"
    output = PdfFileWriter()
    output = get_pdf(html, output=output)
    
    file_name = "{0}.pdf".format(frappe.generate_hash(length=14))
    folder = create_folder("Bohrplaner-Prints", "Home")
    
    filedata = get_file_data_from_writer(output)
    
    _file = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "folder": folder,
        "is_private": 1,
        "content": filedata
    })
    
    _file.save(ignore_permissions=True)
    
    return _file.file_url

"""
In open projects, find conflicts with regional holidays.
"""
def find_holiday_conflicts():
    # get regions
    regions = frappe.get_all("Regional Holidays", fields=['region'])
    
    conflicted_projects = []
    for region in regions:
        # fetch holidays
        holidays_raw = frappe.db.sql("""
                SELECT `holiday_date` AS `date`
                FROM `tabHoliday`
                WHERE `parent` = "{region}"
                  AND `parenttype` = "Regional Holidays"
                  AND `holiday_date` >= CURDATE();
            """.format(region=region['region']), as_dict=True)
            
        holidays = []
        for h in holidays_raw:
            holidays.append(h['date'])
        
        # get all open projects in this region
        projects = frappe.db.sql("""
            SELECT `name`, `expected_start_date`, `expected_end_date`
            FROM `tabProject`
            WHERE
                `status` = "Open"
                AND `object_location` LIKE "%{region}"
                AND `expected_start_date` IS NOT NULL
                AND `expected_end_date` IS NOT NULL
            """.format(region=region['region']), as_dict=True)
        
        for project in projects:
            contained = False
            # check if any holiday is in this planned period
            for h in holidays:
                if (h >= project['expected_start_date']) and (h <= project['expected_end_date']):
                    contained = h
                    continue
            
            if contained:
                conflicted_projects.append(
                    {
                        'project': project['name'],
                        'date': contained,
                        'region': region['region'],
                        'url': get_url_to_form("Project", project['name'])
                    }
                )
            
    return conflicted_projects

"""
In open projects, per drilling team, find overlaps
"""
def find_project_conflicts(drilling_team=None):
    # get drilling teams
    if drilling_team:
        drilling_teams = [{'name': drilling_team}]
    else:
        drilling_teams = frappe.get_all("Drilling Team", filters={'drilling_team_type': 'Bohrteam'}, fields=['name'])
    
    conflicted_projects = []
    # get all open projects in drilling team
    for drilling_team in drilling_teams:
        # get all open projects in this drilling team           # 2023-06-05 removed , "Completed" OVe
        projects = frappe.db.sql("""
            SELECT `name`, `expected_start_date`, `expected_end_date`, `start_half_day`, `end_half_day`
            FROM `tabProject`
            WHERE
                `status` IN ("Open")
                AND `drilling_team` = "{0}"
                AND `expected_start_date` IS NOT NULL
                AND `expected_end_date` >= CURDATE()
                AND `name` NOT LIKE "P-INT-%"
            ORDER BY `expected_start_date` ASC, `name` ASC
            """.format(drilling_team['name']), as_dict=True)
            
        if len(projects) > 1:
            for p in range(0, (len(projects) - 1)):
                if projects[p]['expected_end_date'] > projects[p+1]['expected_start_date'] \
                    or (projects[p]['expected_end_date'] == projects[p+1]['expected_start_date'] and (projects[p]['end_half_day'] == "NM" or projects[p+1]['start_half_day'] == "VM")):
                    # find by conflict affected subcontracting orders, public area uses, cranes and infomails
                    conflicted_projects.append(
                        get_conflict_details(p1=projects[p]['name'], p2=projects[p+1]['name'])
                    )
    
    return conflicted_projects

"""
p1 is the first and p2 the second project
"""
def get_conflict_details(p1, p2):
    p1_doc = frappe.get_doc("Project", p1)
    p2_doc = frappe.get_doc("Project", p2)
    ext_crane_activity = frappe.get_cached_value("Heim Settings", "Heim Settings", "crane_activity")
    
    # find by conflict affected subcontracting orders, public area uses, cranes and infomails
    road_blocks = frappe.db.sql("""
        SELECT 
            `tabRequest for Public Area Use`.`name`,
            `tabRequest for Public Area Use`.`from_date`,
            `tabRequest for Public Area Use`.`to_date`
        FROM `tabRequest for Public Area Use`
        LEFT JOIN `tabRelated Project` ON `tabRelated Project`.`parent` = `tabRequest for Public Area Use`.`name`
        WHERE 
            `tabRequest for Public Area Use`.`project` = "{project}"
            OR `tabRelated Project`.`project` = "{project}"
    """.format(project=p2), as_dict=True)
    
    infomails = frappe.db.sql("""
        SELECT 
            `tabInfomail`.`name`
        FROM `tabInfomail`
        WHERE 
            `tabInfomail`.`project` = "{project}"
    """.format(project=p2), as_dict=True)
    
    crane = None
    for c in p2_doc.checklist:
        if c.activity == ext_crane_activity:
            crane = {
                'crane': c.activity,
                'supplier': c.supplier,
                'supplier_name': c.supplier_name,
                'appointment': c.appointment,
                'appointment_end': c.appointment_end
            }
            
    # find hte next project (adjacent), as this would have a conflict if this conflict is resolved
    adjacent_project = frappe.db.sql("""
        SELECT `name`
        FROM `tabProject`
        WHERE `drilling_team` = "{drilling_team}"
          AND (`expected_start_date` = "{same_day}"
               OR `expected_start_date` = "{next_day}");
    """.format(drilling_team=p2_doc.drilling_team, same_day=p2_doc.expected_end_date,
        next_day=(p2_doc.expected_end_date + timedelta(days=1))), as_dict=True)
    if len(adjacent_project) > 0:
        adjacent_project = adjacent_project[0]['name']
    else:
        adjacent_project = None
        
    return {
        'project': p1,
        'conflict': p2,
        'drilling_team': p2_doc.drilling_team,
        'details': "{0} ({2}) > {1} ({3})".format(p1_doc.expected_end_date, 
            p2_doc.expected_start_date, p1_doc.end_half_day, p2_doc.start_half_day),
        'subprojects': p2_doc.subprojects,
        'road_blocks': road_blocks,
        'crane': crane,
        'infomails': infomails,
        'url': get_url_to_form("Project", p1),
        'adjacent_project': adjacent_project
    }
                    
"""
Find and prerender conflicts
"""
@frappe.whitelist()
def get_conflicts():
    conflicts = {
        'project_conflicts': find_project_conflicts(),
        'holiday_conflicts': find_holiday_conflicts()
    }
    html = frappe.render_template("heimbohrtechnik/heim_bohrtechnik/page/bohrplaner/conflict_dialog.html", conflicts)
    return html

"""
Resolve conflicts of a drilling team
"""
@frappe.whitelist()
def resolve_conflicts(drilling_team, debug=True):
    # prepare trace
    resolution_trace = ""
    # get all conflicts
    conflicts = find_project_conflicts(drilling_team)
    # iterate to resolve conflicts
    while (len(conflicts) > 0):
        # find the later project
        later_project = frappe.get_doc("Project", conflicts[0]['conflict'])
        # determine duration
        start_date = later_project.expected_start_date
        end_date = later_project.expected_end_date
        project_duration = date_diff(end_date, start_date)
        duration = timedelta(days=project_duration)
        # move later project to the end of the earlier project
        later_project.expected_start_date = frappe.get_value("Project", conflicts[0]['project'], 'expected_end_date') + timedelta(days=1)
        # check weekends
        weekday = later_project.expected_start_date.weekday()
        if weekday > 4:         # Sat = 5, Sun = 6
            later_project.expected_start_date = later_project.expected_start_date + timedelta(days=(7 - weekday))
        # move end according to duration
        later_project.expected_end_date = later_project.expected_start_date + duration
        # save
        later_project.save()
        frappe.db.commit()
        # store trace
        resolution_trace += "Moved {p} from {s1}..{e1} to {s2}..{e2} ({p_prev})\n".format(
            p=later_project.name, s1=start_date, e1=end_date, 
            s2=later_project.expected_start_date, e2=later_project.expected_end_date,
            p_prev=conflicts[0]['project'])
        # iterate to find next conflict
        conflicts = find_project_conflicts(drilling_team)
    
    if debug:
        frappe.log_error( resolution_trace, "Resolve conflicts for {0}".format(drilling_team) )
        
    return

"""
Get Subproject Overview for Project Search Dialog
"""
@frappe.whitelist()
def get_subproject_overview(project):
    subprojects = frappe.db.sql("""
                                    SELECT
                                        `subcontracting_order` AS `subproject`,
                                        `start`,
                                        `end`,
                                        `team`,
                                        `description`
                                    FROM `tabProject Subproject`
                                    WHERE `parent` = '{project}'
                                """.format(project=project), as_dict=True)
    if len(subprojects) > 0:
        table = """<p>Mit dem Projekt verknüpfte Unterprojekte:</p>
                    <table style="width:100%;" class="project-search-modal-table">
                        <thead>
                            <tr>
                                <th>Start</th>
                                <th>Ende</th>
                                <th>Team</th>
                                <th>Beschreibung</th>
                            </tr>
                        </thead>
                        <tbody>"""
        for sub_p in subprojects:
            table += """
                        <tr onclick="route_to_subproject(this);" data-subproject="{4}" data-start="{5}">
                            <td>{0}</td>
                            <td>{1}</td>
                            <td>{2}</td>
                            <td>{3}</td>
                        </tr>
                    """.format(frappe.utils.get_datetime(sub_p.start).strftime('%d.%m.%Y'), \
                    frappe.utils.get_datetime(sub_p.end).strftime('%d.%m.%Y'), \
                    sub_p.team, sub_p.description, sub_p.subproject, sub_p.start)
        
        table += """</tbody></table>""".format(subprojects[0].start, subprojects[0].subproject)
        return table
    else:
        return """<p>Keine Unterprojekte vorhanden.</p>"""

@frappe.whitelist()
def get_mfk_overlay_datas(from_date, to_date):
    sql_query = """
                    SELECT 
                    `truck`, 
                    `drilling_team`, 
                    `start_time`, 
                    `end_time`
                    FROM `tabMFK`
                    WHERE `start_time` BETWEEN '{from_date}' AND '{to_date}'
                    OR `end_time` BETWEEN '{from_date}' AND '{to_date}'
                """.format(from_date=from_date, to_date=to_date)
                
    data = frappe.db.sql(sql_query, as_dict=True)
    mfk_data = []
    for entry in data:
        mfk_data.append({
            'truck': entry.truck,
            'drilling_team': entry.drilling_team,
            'start_date': frappe.utils.get_datetime(entry.start_time).strftime('%d.%m.%Y'),
            'start_time': frappe.utils.get_datetime(entry.start_time).strftime('%H:%M:%S'),
            'end_date': frappe.utils.get_datetime(entry.end_time).strftime('%d.%m.%Y'),
            'end_time': frappe.utils.get_datetime(entry.end_time).strftime('%H:%M:%S')
        })
    
    return mfk_data

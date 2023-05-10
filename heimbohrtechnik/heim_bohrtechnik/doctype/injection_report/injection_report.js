// Copyright (c) 2023, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Injection report', {
    refresh: function(frm) {
        
    },
    project: function(frm) {
        autocomplete_object(frm);
    },
    object_name: function(frm) {
    autocomplete_ews(frm);
    },
    sonde: function(frm) {
        autocomplete_needs(frm);
    },
    drilling: function(frm) {
    autocomplete_needs(frm);
    },
    piped_to: function(frm) {
    autocomplete_needs(frm);
    },
    piping: function(frm) {
    autocomplete_needs(frm);
    },
    sonde_length: function(frm) {
    autocomplete_needs(frm);
    },
    need: function(frm) {
    autocomplete_needs(frm);
    },
    needed_ewm: function(frm) {
    autocomplete_needs(frm);
    },
    needed_zement: function(frm) {
    autocomplete_needs(frm);
    },
    needed_bentonit: function(frm) {
    autocomplete_needs(frm);
    },
    gtm_water: function(frm) {
    autocomplete_needs(frm);
    },
    zm_water: function(frm) {
    autocomplete_needs(frm);
    },
    gtm_hs: function(frm) {
    autocomplete_needs(frm);
    },
    zement: function(frm) {
    autocomplete_needs(frm);
    },
    bentonit: function(frm) {
    autocomplete_needs(frm);
    },
    gtm_suspension: function(frm) {
    autocomplete_needs(frm);
    },
    zm_suspension: function(frm) {
        autocomplete_needs(frm);
    },
    gtm_sack_weight: function(frm) {
        autocomplete_needs(frm);
    },
    zm_sack_weight: function(frm) {
        autocomplete_needs(frm);
    },
});

function autocomplete_needs() {
    var need = ((((Math.pow(cur_frm.doc.piping/2,2)*Math.PI/1000)*(cur_frm.doc.piped_to))+((((Math.pow(cur_frm.doc.drilling/2,2)*Math.PI/1000)*(cur_frm.doc.sonde_length-cur_frm.doc.piped_to)-(((((Math.pow(cur_frm.doc.sonde/2,2)*Math.PI/1000)*(cur_frm.doc.sonde_length)*4)))))))));
    cur_frm.set_value('need', Math.round(need));
    if (cur_frm.doc.mortar == "Schwenk Füllbinder GTM-hs" ) {
        cur_frm.set_value('needed_water', Math.round((cur_frm.doc.gtm_water / cur_frm.doc.gtm_suspension)*cur_frm.doc.need));
        cur_frm.set_value('needed_ewm', Math.round((cur_frm.doc.gtm_hs / cur_frm.doc.gtm_suspension)*cur_frm.doc.need));
        cur_frm.set_value('needed_sacks_gtm', Math.round(cur_frm.doc.needed_ewm / cur_frm.doc.gtm_sack_weight));
    } else if (cur_frm.doc.mortar == "Zement-Bentonit" ) {
        cur_frm.set_value('needed_water', Math.round((cur_frm.doc.zm_water / cur_frm.doc.zm_suspension)*cur_frm.doc.need));
        cur_frm.set_value('needed_zement', Math.round((cur_frm.doc.zement / cur_frm.doc.zm_suspension)*cur_frm.doc.need));
        cur_frm.set_value('needed_sacks_zement', Math.round(cur_frm.doc.needed_zement / cur_frm.doc.zm_sack_weight));
        cur_frm.set_value('needed_bentonit', Math.round((cur_frm.doc.bentonit / cur_frm.doc.zm_suspension)*cur_frm.doc.need));
        cur_frm.set_value('needed_sacks_bentonit', Math.round(cur_frm.doc.needed_bentonit / cur_frm.doc.zm_sack_weight));
    }
}

function autocomplete_object(frm) {
    if (frm.doc.project) {
        frappe.call({
            'method': "get_autocomplete_data",
            'doc': frm.doc,
            'args': {
                'project': frm.doc.project
            },
            'callback': function(response) {
                var data = response.message;
                cur_frm.set_value("object_name", data.object.object_name);
                cur_frm.set_value("object_street", data.object.object_street);
                cur_frm.set_value("object_location", data.object.object_location);
                cur_frm.set_value("drilling_team", data.project.drilling_team);
                
                // find addresses
                for (var i = 0; i < data.object.addresses.length; i++) {
                    if (data.object.addresses[i].address_type === "Geologe") {
                        if (data.object.addresses[i].is_simple === 1) {
                            cur_frm.set_value("geologist", 
                                (data.object.addresses[i].simple_name || "") + ", " 
                                    + (data.object.addresses[i].simple_address || ""));
                            cur_frm.set_value("geologist_phone", (data.object.addresses[i].simple_phone || ""));
                            cur_frm.set_value("geologist_email", (data.object.addresses[i].simple_email || ""));
                        } else {
                            cur_frm.set_value("geologist", (data.object.addresses[i].address_display || ""));
                            cur_frm.set_value("geologist_phone", (data.object.addresses[i].phone || ""));
                            cur_frm.set_value("geologist_email", (data.object.addresses[i].email || ""));
                        }
                    }
                }
            }
        });
    }
}

function autocomplete_ews(frm) {
    frappe.call({
            'method': "get_autocomplete_data",
            'doc': frm.doc,
            'args': {
                'project': frm.doc.project
            },
            'callback': function(response) {
                var data = response.message;
    if (data.object.ews_specification.length == 1) {
        cur_frm.set_value("sonde", (data.object.ews_specification[0].ews_diameter || ""));
        cur_frm.set_value("sonde_length", (data.object.ews_specification[0].ews_depth || ""));
    } else if (data.object.ews_specification.length > 1) {
        var options = '';
        for (var i = 0; i < data.object.ews_specification.length; i++) {
            var list_entry = "\n"+(i) + ": " + data.object.ews_specification[i].ews_depth + "m, " + data.object.ews_specification[i].ews_diameter + "mm";
            options += list_entry;
        }
        frappe.prompt([
            {
                "label": "Wähle Bohrung",
                "fieldname": "bohrung",
                "fieldtype": "Select",
                "options": options,
                "reqd": 1
            } ],
            function(values) {
                var x = parseInt(values.bohrung.split(":")[0]);
                cur_frm.set_value("sonde", data.object.ews_specification[x].ews_diameter);
                cur_frm.set_value("sonde_length", data.object.ews_specification[x].ews_depth);
            }
        );
    }
            }
    });
}

-- Auto-generated from ClinicalSummary CCD files
-- Run against your EHR database if the API route is unavailable

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('DB0063','Aizhen','Qi','1950-02-13','F','+1(312)-292-6845','','','','','')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0011','Alan','Beaty','1967-05-01','M','+1(872)-368-4887','alicekvacca2@gmail.com','12728 S Sangamon St','Chicago','IL','60643-6623')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS200','Andrew','Almaraz','1966-01-17','M','+1(773)-664-3439','T19501962@gmail.com','109 e 43rd st apt 202','Chicago','IL','60653')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0096','Bernisteen','Sofowora','1959-02-27','M','+1(708)-475-3721','koolad1234@yahoo.com','10236 S King DR,Apt 1','CHICAGO','IL','60628-2115')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS208','Betty','Johnson','1948-04-09','M','','moorean1992@gmail.com','221 e tulip dr Glenwood il 60425','Chicago','IL','60425')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0077','Brenda','Hampton-Blake','1969-03-26','F','+1(872)-370-2239','Bhamptonblake77@gmail.com','6726 S Loomis Blvd,Apt 1','CHICAGO','IL','60636-2925')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0131','CHARLES','MHOON','1958-10-25','M','+1(872)-353-6115','charlesmhooon58@yahoo.com','5635 S SEELEY','CHICAGO','IL','60636')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0123','CLINTON','SMITH JR','1957-09-11','M','+1(773)-250-0900','clintonsmith15429@gmail.com','135 E 103rd St Apt 8','CHICAGO','IL','60628')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0013','Christine','Kimble','1942-01-29','F','+1(773)-680-7893','llcallnone@gmail.com','11220 S. Homewood Ave.','Chicago','IL','60643')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0111','Dennis','Nowden','1954-11-01','M','+1(773)-993-3952','dennisnowden@gmail.com','9360 S Green ST','CHICAGO','IL','60620-2712')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS220','Dolores','Martinez','1956-05-05','M','+1(464)-249-1705','delomartinez0556@gmail.com','3415 w diversey Ave','Chicago','IL','60647')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0108','Eva','Mitchell','1957-02-28','F','+1(773)-415-2538','Mitchelleva22@yahoo.com','431 W Englewood Ave,Apt 1b','CHICAGO','IL','60621-3254')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS209','GILDA','LASTER','1961-09-09','M','','gildalaster@gmail.com','12640 Fairview Ave Apt 3 blue Islan','Chicago','IL','60406')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS207','GREGORY','CARTER','1960-05-02','M','+1(773)-277-0288','gregcarter931@yahoo.com','4339 W 18TH PL','Chicago','IL','60620')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS225','Gilda','Trader','1953-02-11','M','+1(773)-332-1707','Gildastrader@yahoo.com','10100 s Beverly Ave','Chicago','IL','60643')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0121','Ida','Motes','1955-04-07','F','+1(773)-905-9006','idamotes12@gmail.com','8244 S ADA STREET','Chicago','IL','60620')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS206','JACK','DAVIS','1949-05-17','M','+1(773)-277-0288','RESIDENT.SERVICES@MONTCLARE-SIF.COM','4339 w 18TH PL, CHICAGO IL 60629','Chicago','IL','60629')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0034','JUANITA','MCCAMURY','1972-12-11','M','+1(331)-343-7617','juanita1972@gmail.com','11518 S JUSTINE ST','CHICAGO','IL','60643')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS121','Larry','Hood','1967-09-16','M','+1(847)-571-2058','hoodlarry496@gmail.com','11136 S Sangamon St, Chicago 60643','Chicago','IL','60643')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0104','Lynette','Simon','1959-06-13','F','+1(708)-203-1901','lynettesimon59@gmail.com','14426 S Emerald Ave','RIVERDALE','IL','60827')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0116','MAKENNA','ELECHI','2002-03-05','F','+1(872)-380-5412','makennaelechi23@gmail.com','9415 S WESTERN  AVE,STE 118','CHICAGO','IL','60643')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0120','Margaret','Morris','1952-02-22','F','+1(773)-758-8917','mhillmorris52@gmail.com','646 E 93rd st','Chicago','IL','60619')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0133','Marshall','OLIPHANT','1959-06-15','M','','marshalloliphant322@gmail.com','9901 S YALE AVE','CHICAGO','IL','60628')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0070','Marvin','Fleming','1963-08-07','M','+1(773)-663-9238','fleminglee31@gmail.com','7139 S Emerald St,2ND FL','CHICAGO','IL','60607-2339')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0092','Michael','Isaac','1970-09-28','M','+1(847)-269-0812','micheallisaac9@gmail.com','6930 S South Shore Dr','CHICAGO','IL','60649-1835')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0060','PAMELA','WARD','1947-03-23','F','+1(872)-380-7835','pw136359@gmail.com','8123 S INGLESIDE AVE,APT 1','CHICAGO','IL','60619-5224')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS201','Phillip','Martin','1954-06-10','M','+1(773)-559-7745','philmart5410@gmail.com','1537 W. 79th St (Apt 2W)','Chicago','IL','06062')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0112','Renee','Prentiss','1956-09-10','M','+1(773)-512-0025','rmjprentiss@gmail.com','6700 S SOUTH SHORE DR,APT 17D','CHICAGO','IL','60639-1313')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0126','Richard','Malone','1961-09-06','M','+1(773)-218-1818','randyj347@gmail.com','661 E 69th St Apt 14','CHICAGO','IL','60637')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0122','Richard','Whirl','1965-04-08','M','+1(224)-469-6449','rlwhirl@gmail.com','7952 S ASHLAND AVE,2R','Chicago','IL','60620')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0109','Ronald','Harris','1962-02-15','M','+1(312)-388-4675','rondadon73@gmail.com','7730 S Hoyne Ave','CHICAGO','IL','60620-5739')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0107','Russell','Townsend','1963-09-04','M','+1(773)-891-3111','afiawatts@gmail.com','5300 S Hyde park Blvd,Apt 101','CHICAGO','IL','60615-5717')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0129','SARAH','WALTERS','1994-07-02','F','+1(309)-635-0192','sarawaters21@gmail.com','720W JOAN CT','PEORIA','IL','61614')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0103','SHARON','ADAMS','1959-12-25','M','+1(312)-961-1193','naadams0111@gmail.com','5928 S WINCHESTER AVE,BASEMENT','CHICAGO','IL','60636')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0105','SHERE','FOSTER','1980-02-20','F','+1(708)-522-7631','sherrie35.sf@gmail.com','12147 s normal Ave','CHICAGO','IL','60628-6309')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0114','TIA','STROKES','2000-12-04','F','','mimij402@gmail.com','1408 EAST 72ND PL,APT 1','CHICAGO','IL','60619')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0019','TORRIE','FARRELL','1965-02-10','M','+1(773)-983-0381','','7934 S BISHOP ST','CHICAGO','IL','60620-3839')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0079','Tina','ANDREWS DAVIS','1967-03-13','F','+1(630)-914-4626','19ttdavis345@gmail.com','450 Rothbury Dr','BOLINGBROOK','IL','60440-2253')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0117','Toleus','McCullum','1960-04-13','M','+1(773)-815-0563','Toleusmccullum458@gmail.com','825 N Christiana ave','Chicago','IL','60615')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('MIS203','William','Brown','1950-03-06','M','+1(773)-664-7270','wilbrown1950@gmail.com','10006 S Lafayette','Chicago','IL','60628')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0128','burnett','cousins','1964-07-06','M','','burnettcouins@gmail.com','12301 S Bishop St Apt 13','RIVERDALE','IL','60827')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;

INSERT INTO patients (mrn, first_name, last_name, dob, sex, phone, email, address_line, city, state, zip) VALUES ('Mis0132','richard','carter','1971-04-06','M','','','','','','')
ON CONFLICT (mrn) DO UPDATE SET first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name, dob=EXCLUDED.dob, phone=EXCLUDED.phone, email=EXCLUDED.email;


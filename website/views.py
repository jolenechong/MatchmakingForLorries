from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for
from flask_login import login_required, logout_user, current_user
from .models import User, Warehouse, Request, Lorry, Notification, Matched
from . import db
from datetime import datetime
import pandas as pd
from openpyxl import Workbook

# setting up blueprint
views = Blueprint('views', __name__)


def shortest_path(nodes, distances, current):
    unvisited = dict.fromkeys(nodes)
    path = dict.fromkeys(nodes)
    visited = {}
    currentDistance = 0
    unvisited[current] = currentDistance
    while True:
        for neighbour, distance in distances[current].items():
            if neighbour not in unvisited: 
                continue
            newDistance = currentDistance + distance
            if unvisited[neighbour] is None or unvisited[neighbour] > newDistance:
                path[neighbour] = current
                unvisited[neighbour] = newDistance
        visited[current] = currentDistance
        del unvisited[current]
        if not unvisited: 
            break
        candidates = [node for node in unvisited.items() if node[1]]
        if candidates:
            current, currentDistance = sorted(candidates, key = lambda x: x[1])[0]
    return [visited, path]


def find_path(dict, start, end):
    i = end
    path = [end]
    while i != start:
        path.append(dict[i])
        i = dict[i]
    return path


def search(weight, location, destination, operator):
    all_requests = Request.query.filter_by(end_location=destination, status='Finding match')
    all_lorries = Lorry.query.filter_by(status='waiting')
    adj_list = {}
    if all_requests:
        all_warehouses = Warehouse.query.all()
        nodes = [x.location for x in all_warehouses]
        adj_list = {}
        request_warehouses = [x.warehouse_location for x in all_requests]
        for i in nodes:
            j = Warehouse.query.get(i)
            edges = {j.north_south: j.ns_weight, j.east: j.e_weight, j.west: j.w_weight, j.north_south_extra: j.ns_weight_extra}
            edges_final = {k: v for k, v in edges.items() if v is not None}
            adj_list[i] = edges_final
        distance = shortest_path(nodes, adj_list, location)
        path = find_path(distance[1], location, destination)
        keys = list(distance[0].keys())
        sorted_warehouses = [y for y in keys if y not in path]
        path.extend(sorted_warehouses)
        for p in path:
            if p in request_warehouses:
                requests = Request.query.filter_by(warehouse_location=p, status='Finding match', end_location=destination).order_by(Request.closing_time)
                for r in requests:
                    total = int(weight) + r.load_weight
                    for lorry in [z for z in all_lorries if z.user_id==operator or z.user_id==r.user_id]:
                        if 0 <= lorry.total_load - total <= lorry.total_load*0.2:
                            return lorry.plate_number, r.id, r.user_id
    return None


@views.route('/add-request', methods=['GET', 'POST'])
@login_required
def addrequest():
    if request.method == 'POST':
        req = request.form
        destination = req.get('to')
        location = req.get('from')
        user = User.query.filter_by(email=current_user.email).first()

        if Warehouse.query.filter_by(location=location).first():
            if Warehouse.query.filter_by(location=destination).first():
                weight = req.get('load_weight')
                time = req.get('closing_time')
                datetime_str = time[5:7] + '/' + time[8:10] + '/' + time[2:4] + ' ' + time[11:] + ':00'
                datetime_object = datetime.strptime(datetime_str, '%m/%d/%y %H:%M:%S')
                result = search(weight, location, destination, user.id)

                if result:
                    status = 'Pending delivery'
                    new_notif = Notification(user_id=result[2], request_status=status, request_id=result[1])
                    db.session.add(new_notif)
                    lorry = Lorry.query.get(result[0])
                    lorry.status = 'busy'
                    matched_request = Request.query.get(result[1])
                    matched_request.status = 'Pending delivery'
                else:
                    status = 'Finding match'

                add_request = Request(status=status, load_weight=weight, end_location=destination, closing_time=datetime_object, warehouse_location=location, user_id=user.id)
                db.session.add(add_request)
                db.session.commit()

                if result:
                    notif = Notification(user_id=user.id, request_status=status, request_id=add_request.id)
                    db.session.add(notif)
                    match = Matched(first_request_id=add_request.id, second_request_id=result[1], lorry_plate_number=result[0])
                    db.session.add(match)
                    db.session.commit()
                return redirect(url_for('views.results', request_id=add_request.id))
            else:
                flash("Invalid 'to' location entered")
        else:
            flash("Invalid 'from' location entered")
    return render_template('addRequest.html',user=current_user, warehouse=Warehouse.query.all())


@views.route('/results/<request_id>')
@login_required
def results(request_id):
    my_request = Request.query.get(request_id)
    my_info = User.query.get(my_request.user_id)
    request = Matched.query.filter_by(first_request_id=request_id).first()
    if request:
        matched_request = Request.query.get(request.second_request_id)
    if not request:
        request = Matched.query.filter_by(second_request_id=request_id).first()
        if request:
            matched_request = Request.query.get(request.first_request_id)
    if request:
        matched_info = User.query.get(matched_request.user_id)
        lorry = Lorry.query.get(request.lorry_plate_number)
        lorry_location = Warehouse.query.get(lorry.warehouse_id)
        return render_template('results.html', user=my_info, user2=matched_info, request=my_request, request2=matched_request, lorry=lorry, lorry_location=lorry_location, error='')
    return render_template('results.html', error='error', user=my_info)


@views.route('/')
@login_required
def home():
    return render_template('home.html', user=current_user)


@views.route('/lorry-status', methods=['POST','GET'])
def lorry_status():
    if request.method == 'POST':
        req = request.form
        status = req.get('status')
        plate_number = req.get('plate_number')
        
        # get lorry according to plate number
        lorry = Lorry.query.filter_by(plate_number=plate_number).first()
        # change status of that lorry
        lorry.status = status

        if status == "Delivered":
            matched = Matched.query.filter_by(lorry_plate_number=plate_number).order_by(Matched.id.desc()).first()
            firstreq = matched.first_request_id
            secondreq = matched.second_request_id

            firstquery = Request.query.get(firstreq)
            firstquery.status = "Delivered"
            firstnotif = Notification(user_id=firstquery.user_id, request_id=firstreq, request_status='Delivered')
            db.session.add(firstnotif)

            secondquery = Request.query.get(secondreq)
            secondquery.status = "Delivered"
            secondnotif = Notification(user_id=secondquery.user_id, request_id=secondreq, request_status='Delivered')
            db.session.add(secondnotif)
            
            lorry.status = "waiting"
            db.session.commit()

        db.session.commit()
        return render_template('updateLorry.html', user=current_user, result='success')


    return render_template('updateLorry.html', user=current_user, result='')

# load excel file
@views.route('/excel', methods=['GET', 'POST'])
@login_required
def exportexcel():
    # get data for all requests according to current user
    user = User.query.filter_by(email=current_user.email).first()
    data = Request.query.filter_by(user_id=user.id)
    id_list = []
    enter_date = []
    load_weight = []
    end_location = []
    closing_time = []
    status = []
    
    for request in data:
        id_list.append(request.id)
        enter_date.append(request.enter_date)
        load_weight.append(request.load_weight)
        end_location.append(request.end_location)
        closing_time.append(request.closing_time)
        status.append(request.status)

    d = { 'id': id_list,'enter date':enter_date, 'load weight': load_weight, 'end location':end_location,
        'closing_time': closing_time, 'status': status}

    df = pd.DataFrame(data=d)

    with pd.ExcelWriter("Requests_data.xlsx") as writer:
        df.to_excel(writer)

    return "File loaded, open directory and look for Requests_data.xlsx"


# insert fake values for warehouses and lorries
def add():
    user = User.query.filter_by(email=current_user.email).first()

    add1 = Lorry(plate_number='SG12JDFS',total_load=60, status='waiting', warehouse_id='#01-101', user_id=user.id)
    add2 = Lorry(plate_number='SG22HDYF',total_load=100, status='waiting', warehouse_id='#01-103', user_id=user.id)
    add3 = Lorry(plate_number='SG35HDYF',total_load=100, status='busy', warehouse_id='#01-101', user_id=user.id)
    add4 = Lorry(plate_number='SG45HDYF',total_load=60, status='waiting', warehouse_id='#02-110', user_id=user.id)
    db.session.add(add1)
    db.session.add(add2)
    db.session.add(add3)
    db.session.add(add4)
    db.session.commit()


@views.route('/add-lorries')
def yes():
    add()
    return 'lorries added!'


@views.route('/add-warehouses')
def tired():
    add1 = Warehouse(location='#01-101', north_south='#01-114', ns_weight=3, east='#01-102', e_weight=1, west='#02-103', w_weight=5)
    add2 = Warehouse(location='#01-102', north_south='#01-113', ns_weight=3, east='#01-103', e_weight=1, west='#01-101', w_weight=1)
    add3 = Warehouse(location='#01-103', north_south='#01-112', ns_weight=2, east='#01-104', e_weight=1, west='#01-102', w_weight=1)
    add4 = Warehouse(location='#01-104', north_south='#01-111', ns_weight=2, east='#01-105', e_weight=1, west='#01-103', w_weight=1)
    add5 = Warehouse(location='#01-105', north_south='#01-110', ns_weight=3, east='#01-106', e_weight=1, west='#01-104', w_weight=1)
    add6 = Warehouse(location='#01-106', north_south='#01-109', ns_weight=3, east='#01-107', e_weight=1, west='#01-105', w_weight=1)
    add7 = Warehouse(location='#01-107', west='#01-106', w_weight=1, north_south_extra='#01-109', ns_weight_extra=3)
    add8 = Warehouse(location='#01-109', north_south='#01-106', ns_weight=3, east='#01-125', e_weight=4, west='#01-110', w_weight=1, north_south_extra='#01-107', ns_weight_extra=3)
    add9 = Warehouse(location='#01-110', north_south='#01-105', ns_weight=3, east='#01-109', e_weight=1, west='#01-111', w_weight=1)
    add10 = Warehouse(location='#01-111', north_south='#01-104', ns_weight=3, east='#01-110', e_weight=1, west='#01-112', w_weight=1)
    add11 = Warehouse(location='#01-112', north_south='#01-103', ns_weight=3, east='#01-111', e_weight=1, west='#01-113', w_weight=1, north_south_extra='#01-116', ns_weight_extra=4)
    add12 = Warehouse(location='#01-113', north_south='#01-102', ns_weight=3, east='#01-112', e_weight=1, west='#01-114', w_weight=1, north_south_extra='#01-115', ns_weight_extra=4)
    add13 = Warehouse(location='#01-114', north_south='#01-101', ns_weight=3, east='#01-113', e_weight=1, west='#02-103', w_weight=5, north_south_extra='#01-115', ns_weight_extra=4)
    add14 = Warehouse(location='#01-115', north_south='#01-114', ns_weight=4, east='#01-116', e_weight=1, west='#02-101', w_weight=5, north_south_extra='#01-113', ns_weight_extra=4)
    add15 = Warehouse(location='#01-116', north_south='#01-112', ns_weight=4, east='#01-117', e_weight=6, west='#01-115', w_weight=1)
    add16 = Warehouse(location='#01-117', north_south='#01-122', ns_weight=4, east='#01-118', e_weight=1, west='#01-116', w_weight=6, north_south_extra='#01-121', ns_weight_extra=4)
    add17 = Warehouse(location='#01-118', north_south='#01-120', ns_weight=4, west='#01-117', w_weight=1)
    add18 = Warehouse(location='#01-120', north_south='#01-131', ns_weight=3, west='#01-121', w_weight=1, north_south_extra='#01-118', ns_weight_extra=4)
    add19 = Warehouse(location='#01-121', north_south='#01-130', ns_weight=3, east='#01-120', e_weight=1, west='#01-122', w_weight=1, north_south_extra='#01-117', ns_weight_extra=4)
    add20 = Warehouse(location='#01-122', north_south='#01-129', ns_weight=3, east='#01-121', e_weight=1, west='#01-123', w_weight=1, north_south_extra='#01-117', ns_weight_extra=4)
    add21 = Warehouse(location='#01-123', north_south='#01-128', ns_weight=3, east='#01-122', e_weight=1, west='#01-124', w_weight=1)
    add22 = Warehouse(location='#01-124', north_south='#01-127', ns_weight=3, east='#01-123', e_weight=1, west='#01-125', w_weight=1)
    add23 = Warehouse(location='#01-125', north_south='#01-126', ns_weight=3, east='#01-124', e_weight=1, west='#01-109', w_weight=4)
    add24 = Warehouse(location='#01-126', north_south='#01-125', ns_weight=3, east='#01-127', e_weight=1)
    add25 = Warehouse(location='#01-127', north_south='#01-124', ns_weight=3, east='#01-128', e_weight=1, west='#01-126', w_weight=1)
    add26 = Warehouse(location='#01-128', north_south='#01-123', ns_weight=3, east='#01-129', e_weight=1, west='#01-127', w_weight=1)
    add27 = Warehouse(location='#01-129', north_south='#01-122', ns_weight=3, east='#01-130', e_weight=1, west='#01-128', w_weight=1)
    add28 = Warehouse(location='#01-130', north_south='#01-121', ns_weight=3, east='#01-131', e_weight=1, west='#01-129', w_weight=1)
    add29 = Warehouse(location='#01-131', north_south='#01-120', ns_weight=3, west='#01-130', w_weight=1)
    add30 = Warehouse(location='#02-101', north_south='#02-103', ns_weight=4, east='#02-102', e_weight=1, west='#01-115', w_weight=5)
    add31 = Warehouse(location='#02-102', north_south='#02-104', ns_weight=4, east='#02-113', e_weight=6, west='#02-101', w_weight=1)
    add32 = Warehouse(location='#02-103', north_south='#02-101', ns_weight=4, east='#02-104', e_weight=1, west='#01-114', w_weight=5, north_south_extra='#01-101', ns_weight_extra=5)
    add33 = Warehouse(location='#02-104', north_south='#02-102', ns_weight=4, east='#02-105', e_weight=1, west='#02-103', w_weight=1)
    add34 = Warehouse(location='#02-105', east='#02-106', e_weight=1, west='#02-104', w_weight=1)
    add35 = Warehouse(location='#02-106', east='#02-107', e_weight=1, west='#02-105', w_weight=1)
    add36 = Warehouse(location='#02-107', east='#02-108', e_weight=4, west='#02-106', w_weight=1)
    add37 = Warehouse(location='#02-108', east='#02-109', e_weight=1, west='#02-107', w_weight=4)
    add38 = Warehouse(location='#02-109', east='#02-110', e_weight=1, west='#02-108', w_weight=1)
    add39 = Warehouse(location='#02-110', east='#02-111', e_weight=1, west='#02-109', w_weight=1)
    add40 = Warehouse(location='#02-111', north_south='#02-113', ns_weight=4, east='#02-112', e_weight=1, west='#02-110', w_weight=1)
    add41 = Warehouse(location='#02-112', north_south='#02-114', ns_weight=4, west='#02-111', w_weight=1)
    add42 = Warehouse(location='#02-113', north_south='#02-111', ns_weight=4, east='#02-114', e_weight=1, west='#02-102', w_weight=6)
    add43 = Warehouse(location='#02-114', north_south='#02-112', ns_weight=4, west='#02-113', w_weight=1)
    db.session.add(add1)
    db.session.add(add2)
    db.session.add(add3)
    db.session.add(add4)
    db.session.add(add5)
    db.session.add(add6)
    db.session.add(add7)
    db.session.add(add8)
    db.session.add(add9)
    db.session.add(add10)
    db.session.add(add11)
    db.session.add(add12)
    db.session.add(add13)
    db.session.add(add14)
    db.session.add(add15)
    db.session.add(add16)
    db.session.add(add17)
    db.session.add(add18)
    db.session.add(add19)
    db.session.add(add20)
    db.session.add(add21)
    db.session.add(add22)
    db.session.add(add23)
    db.session.add(add24)
    db.session.add(add25)
    db.session.add(add26)
    db.session.add(add27)
    db.session.add(add28)
    db.session.add(add29)
    db.session.add(add30)
    db.session.add(add31)
    db.session.add(add32)
    db.session.add(add33)
    db.session.add(add34)
    db.session.add(add35)
    db.session.add(add36)
    db.session.add(add37)
    db.session.add(add38)
    db.session.add(add39)
    db.session.add(add40)
    db.session.add(add41)
    db.session.add(add42)
    db.session.add(add43)
    db.session.commit()
    return 'Added!'

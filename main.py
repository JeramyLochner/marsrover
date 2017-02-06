import requests
from datetime import datetime
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy

rovers = {"curiosity": ["ALL", "FHAZ", "RHAZ", "MAST", "CHEMCAM",
                        "MAHLI", "MARDI", "NAVCAM"],
          "opportunity": ["ALL", "FHAZ", "RHAZ", "NAVCAM", "PANCAM",
                          "MINITES"],
          "spirit": ["ALL", "FHAZ", "RHAZ", "NAVCAM", "PANCAM",
                     "MINITES"]}

app = Flask(__name__)
app.config.from_envvar('NASA_CONFIG')
db = SQLAlchemy(app)


def verify_sol_date(sol):
    # Verify sol data is in the correct format
    if sol is None:
        return False
    try:
        s = int(sol)
        if s > 0 and s < 100000:
            return True
    except ValueError:
        return False
    return False


def verify_earth_date(earth_date):
    # Verify earth date is in the correct format
    try:
        dt = datetime.strptime(earth_date, "%Y-%m-%d")
        if dt:
            return True
    except ValueError:
        return False
    return False


def check_search(rover, camera, earth=None, sol=None):
    # Checks if a search is cached
    if earth is not None:
        search = Search.query.filter_by(rover=rover, camera=camera,
                                        earth=earth, sol="-").first()
    else:
        search = Search.query.filter_by(rover=rover, camera=camera,
                                        earth="-", sol=sol).first()
    if search:
        return True
    return False


def get_pictures(rover, camera, sol=None, earth=None):
    # Grabs images through the api
    if sol is None and earth is None:
        return {"errors": "no date provided"}
    rover = rover.lower()
    camera = camera.upper()
    if rover not in rovers or camera not in rovers[rover]:
        return {"errors": "invalid camera or rover"}
    url = "https://api.nasa.gov/mars-photos/api/v1/rovers/"
    url += rover
    url += "/photos?"
    if verify_sol_date(sol):
        url += "sol=" + str(sol)
    elif verify_earth_date(earth):
        url += "earth_date=" + str(earth)
    else:
        return {"errors": "failed date validation"}
    if camera != "ALL":
        url += "&camera="
        url += camera
    url += "&api_key="
    url += app.config['API_KEY']

    try:
        return requests.get(url).json()
    except ValueError:
        return None


def get_urls(rover, camera, sol="-", earth="-"):
    # Checks cache for your search, fails over to grabbing images from api
    # then adding them to the cache
    if earth is not None and check_search(rover, camera, earth=earth):
        if camera != "ALL":
            images = Image.query.filter_by(rover=rover,
                                           camera=camera,
                                           earth=earth).all()
        else:
            images = Image.query.filter_by(rover=rover, earth=earth).all()
    elif sol is not None and check_search(rover, camera, sol=sol):
        if camera != "ALL":
            images = Image.query.filter_by(rover=rover,
                                           camera=camera,
                                           sol=sol).all()
        else:
            images = Image.query.filter_by(rover=rover, sol=sol).all()
    else:
        j = get_pictures(rover, camera, earth=earth, sol=sol)
        if earth:
            s = Search(rover, camera, earth=earth)
        else:
            s = Search(rover, camera, sol=sol)
        db.session.add(s)
        if 'errors' not in j:
            images = []
            for pic in j['photos']:
                img = Image(int(pic['id']),
                            pic['rover']['name'].lower(),
                            pic['camera']['name'].upper(),
                            pic['img_src'],
                            earth=earth,
                            sol=sol)
                if camera != "ALL":
                    db.session.add(img)
                images.append(img)
        else:
            return [None, j['errors']]

    urls = []
    for image in images:
        urls.append(str(image.src))
    db.session.commit()
    return urls


class Search(db.Model):
    # Search cache table
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rover = db.Column(db.String(12))
    camera = db.Column(db.String(10))
    earth = db.Column(db.String(12))
    sol = db.Column(db.String(16))

    def __init__(self, rover, camera, earth="-", sol="-"):
        self.rover = rover
        self.camera = camera
        self.earth = earth
        self.sol = sol

    def __repr__(self):
        return '<Search {}, {}, {}, {}>'.format(self.rover,
                                                self.camera,
                                                self.earth,
                                                self.sol)


class Image(db.Model):
    # Image cache table
    id = db.Column(db.Integer, primary_key=True)
    rover = db.Column(db.String(12))
    camera = db.Column(db.String(10))
    src = db.Column(db.String(240), unique=True)
    earth = db.Column(db.String(12))
    sol = db.Column(db.String(16))

    def __init__(self, id, rover, camera, src, earth="-", sol="-"):
        self.id = id
        self.rover = rover
        self.camera = camera
        self.src = src
        self.earth = earth
        self.sol = sol
        if earth is None:
            self.earth = "-"
        if sol is None:
            self.sol = "-"

    def __repr__(self):
        return '<Image {}, {}, {}, {}, {}>'.format(self.id,
                                                   self.rover,
                                                   self.camera,
                                                   self.earth,
                                                   self.sol)


@app.route('/', methods=['POST', 'GET'])
def main():
    # GET just returns the page
    if request.method == 'GET':
        return render_template('index.html', defaults={"rover": "Curiosity",
                                                       "camera": "FHAZ",
                                                       "date": ""})
    # Otherwise look at their chosen options and add the images
    earth = "-"
    sol = "-"
    # Image.query.delete()
    # Search.query.delete()
    camera = request.form.get('cameraOption').upper()
    rover = request.form.get('roverOption').lower()
    error = None
    date = request.form['dateOption']
    urls = []
    try:
        date = int(date)
        sol = date
    except ValueError:
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            if dt:
                earth = date
        except ValueError:
            error = "Not a valid date"
    urls = get_urls(rover, camera, sol=sol, earth=earth)
    if urls and urls[0] is None:
        error = urls[1]
    if error:
        return render_template('index.html', error=error,
                               defaults={"rover": str(rover).title(),
                                         "camera": str(camera).upper(),
                                         "date": date})
    return render_template('index.html', urls=urls,
                           defaults={"rover": str(rover).title(),
                                     "camera": str(camera).upper(),
                                     "date": date})

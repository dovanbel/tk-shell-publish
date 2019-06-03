# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
import os
import re
import shutil
import glob

import tank
# by importing QT from sgtk rather than directly, we ensure that
# the code will be compatible with both PySide and PyQt.
from sgtk.platform.qt import QtCore, QtGui
from .ui.dialog import Ui_Dialog


from .model_entity import SgEntityModel
from .proxymodel_entity import SgEntityProxyModel


shotgun_model = sgtk.platform.import_framework("tk-framework-shotgunutils", "shotgun_model") 
overlay = sgtk.platform.import_framework("tk-framework-qtwidgets", "overlay_widget") 

imgExtension = [".jpg", ".tx", ".hdr", ".tif", ".exr", ".tga"]

def show_dialog(app_instance):
    """
    Shows the main dialog window.
    """
    # in order to handle UIs seamlessly, each toolkit engine has methods for launching
    # different types of windows. By using these methods, your windows will be correctly
    # decorated and handled in a consistent fashion by the system. 
    
    # we pass the dialog class to this method and leave the actual construction
    # to be carried out by toolkit.
    app_instance.engine.show_dialog("Publish Area", app_instance, AppDialog)
    


class DropWidget(QtGui.QFrame):
    def __init__(self, parent=None):
        super(DropWidget, self).__init__(parent)
        self.setMinimumSize(600, 200)
        self.setFrameStyle(QtGui.QFrame.Sunken | QtGui.QFrame.StyledPanel)
        self.setAcceptDrops(True)

        self.main = parent

        self._overlay = overlay.ShotgunOverlayWidget(self)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
    
    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event):
        try:
            

            toPublish = []

            tmp_item = self.main._get_selected_entity()

            if not tmp_item:
                self._overlay.show_error_message("No task selected")
                return

            parent_tmp_item = tmp_item.parent()

            if not parent_tmp_item:
                self._overlay.show_error_message("No asset detected")
                return

            field_parent_data = shotgun_model.get_sanitized_data(parent_tmp_item, SgEntityModel.SG_ASSOCIATED_FIELD_ROLE)            


            field_data = shotgun_model.get_sanitized_data(tmp_item, SgEntityModel.SG_ASSOCIATED_FIELD_ROLE)

            print field_parent_data
            print field_data
 
            if field_parent_data["name"] != "entity":
                return

            entity_asset = field_parent_data["value"]
            task = field_data["value"]

            self._overlay.start_spin()
            app = sgtk.platform.current_bundle()
            tk = app.engine.tank

            if entity_asset["type"] == "Shot":
                entity =  tk.shotgun.find_one("Shot", filters=[["id", "is", entity_asset["id"]]])

                task_entity = tk.shotgun.find_one("Task", filters=[["entity", "is", entity], ["content", "is", task ] ], fields=["step.Step.short_name"])

                stepShortName = task_entity["step.Step.short_name"]

                ctx = tk.context_from_entity("Task", task_entity["id"])
                for url in event.mimeData().urls():
                    publishing = True
                    path = str(url.toLocalFile())
                    if os.path.isfile(path):
                        base, ext = os.path.splitext(os.path.basename(path))
                        template_path = None
                        work_template_path = None                    


                        if path.endswith(".abc"):
                            template_path = tk.templates['maya_shot_mesh_alembic_cache']
                        elif path.endswith(".mb") or path.endswith(".ma"):
                            template_path = tk.templates['maya_shot_publish']
                            work_template_path = tk.templates['maya_shot_work']
                        elif path.endswith(".xml") :
                            template_path = tk.templates['maya_shot_ncache']
                            #copySequence = path.
                        else:
                            continue

                        fields = {}

                        fields["Shot"] = entity_asset["name"]

                        if "name" in template_path.keys:
                            exp = "(.+)_[Vv]*\d+"
                            m = re.search(exp, base)
                            if m:
                                base = m.group(1)

                            nameScene, ok = QtGui.QInputDialog.getText (self, "Enter a name for %s" % base, "Name for %s :" % base, QtGui.QLineEdit.Normal, "")
                            if "_" in nameScene:
                                nameScene = nameScene.replace("_", "-")
                            if nameScene == "" and template_path.is_optional("name") == False:
                                self._overlay.show_error_message("Name is mandatory")
                                return
                            if nameScene != "":
                                fields["name"] = nameScene

                        fields["Step"] = stepShortName

                        version = 0
                        publishedFiles = tk.paths_from_template(template_path, fields, ["version"], skip_missing_optional_keys=True) 

                        for publishedFile in publishedFiles:
                            fields_file = template_path.get_fields(publishedFile)
                            if "version" in fields_file: 
                                if fields_file["version"] > version:
                                    version = fields_file["version"]

                        fields["version"] = version + 1

                        destPath = template_path.apply_fields(fields)

                        # creating the path if it doesn't exists.
                        if not os.path.exists(os.path.dirname(destPath)): 
                            os.makedirs(os.path.dirname(destPath))

                        thumbnail = None
                        convertionLine = None
                        thumbnailGenerator = None
                        if path.endswith(".abc"):
                            tank_type = "Alembic Cache"
                            #convertionLine = "//server01/shared/sharedShotgun/abcconvert.exe -force -toOgawa %s %s" % (path, destPath)
                            thumbnail = path.replace(".abc", ".jpg")
                        elif path.endswith(".obj"):
                            tank_type = "Alembic Cache"
                            convertionLine = "//server01/shared/sharedShotgun/WFObjConvert_obj2abc.exe %s %s" % (path, destPath)
                            thumbnail = path.replace(".obj", ".jpg")                    
                        elif path.endswith(".mb") or path.endswith(".ma"):
                            tank_type = "Maya %s" % stepShortName
                        elif path.endswith(".xml") :
                            tank_type = "nCache Xml"

                        if convertionLine:
                            os.system(convertionLine)
                        else:
                            shutil.copyfile(path, destPath)

                        if thumbnailGenerator:
                            os.system(thumbnailGenerator)

                        # get all the assets for the project
                        if path.endswith(".abc") or path.endswith(".obj"):
                            if "name" in fields:
                                name = "%s_%s_%s" % (fields["Shot"], fields["name"], fields["Step"])
                        else:
                            if "name" in fields and fields["name"]:
                                name = fields["name"]
                            else:
                                name = fields["Shot"]

                        args = {
                            "tk": tk,
                            "context": ctx,
                            "comment": "",
                            "path": destPath,
                            "name": name,
                            "thumbnail_path": thumbnail,
                            "version_number": fields["version"],
                            "published_file_type":tank_type,
                        }
                        

                        if publishing:
                            toPublish.append(args)
                            
                            if tank_type == "nCache Xml" :
                                xmlBasename, ext = os.path.splitext(os.path.basename(destPath))

                                srcBase, ext = os.path.splitext(os.path.basename(path))
                                srcDir = os.path.dirname(path) 
                                destDir = os.path.dirname(destPath)
                                
                                for src in glob.glob(srcDir+"/"+srcBase+"*.mc"  ) :
                                    
                                    dst = src.replace(srcDir,destDir)
                                    dst = dst.replace(  srcBase ,xmlBasename   )
                                    shutil.copy(src,dst)

                            # we must create a work file too
                            if work_template_path:
                                fields["version"] = fields["version"] + 1
                                destPathWork = work_template_path.apply_fields(fields)   
                                if not os.path.exists(os.path.dirname(destPathWork)): 
                                    os.makedirs(os.path.dirname(destPathWork))

                                shutil.copyfile(destPath, destPathWork)




                for args in toPublish:
                    sgtk.util.register_publish(**args)                                        



            elif entity_asset["type"] == "Asset":
                entity =  tk.shotgun.find_one("Asset", filters=[["id", "is", entity_asset["id"]]], fields=["sg_asset_type"])
                entityType = entity["sg_asset_type"]

                task_entity = tk.shotgun.find_one("Task", filters=[["entity", "is", entity], ["content", "is", task ] ], fields=["step.Step.short_name"])
                ctx = tk.context_from_entity("Task", task_entity["id"])
                stepShortName = task_entity["step.Step.short_name"]

                for url in event.mimeData().urls():
                    publishing = True
                    path = str(url.toLocalFile())
                    if os.path.isfile(path):
                        base, ext = os.path.splitext(os.path.basename(path))
                        template_path = None
                        work_template_path = None
                        if path.endswith(".abc") or path.endswith(".obj") :
                            template_path = tk.templates['maya_asset_mesh_alembic_cache']
                        elif path.endswith(".mb") or path.endswith(".ma"):
                            template_path = tk.templates['maya_asset_publish']
                            work_template_path = tk.templates['maya_asset_work']
                        elif ext in imgExtension:
                            template_path = tk.templates['asset_publish_area_textures']
                        else:
                            self._overlay.show_error_message("File extension %s not recognized" % ext)
                            continue
                        fields = {}

                        fields["Asset"] = entity_asset["name"].replace(" ", "-")
                        fields["sg_asset_type"] = entityType


                        if ext in imgExtension:
                            if entityType != "HDRi":
                                #check for UDIM
                                exp = "(.+)\.(\d{4})"
                                m = re.search(exp, base)
                                if m:
                                    fields["udim"] = int(m.group(2))
                                    base = m.group(1)

                            #check for VERSION
                            exp = "(.+)_[Vv]*\d+"
                            m = re.search(exp, base)
                            if m:
                                base = m.group(1)

                            parts = base.split("_")

                            imageType = None
                            if entityType == "HDRi":
                                imageType = "HDR"
                            for part in parts:
                                if part in template_path.keys['imagetype'].choices:
                                    imageType = part

                            if not imageType:
                                item, ok = QtGui.QInputDialog.getItem(None, "Select Image type for %s..." % base, "Type of %s:" % base, template_path.keys['imagetype'].choices, 0, False)          
                                if ok:
                                    imageType = item
                                else:
                                    continue

                            parts.remove(imageType)
                            fields["imagetype"] = imageType

                            for i, c in enumerate(parts):
                                parts[i] = c.capitalize()

                            fields["name"] = "".join(parts)


                        elif "name" in template_path.keys:
                            exp = "(.+)_[Vv]*\d+"
                            m = re.search(exp, base)
                            if m:
                                base = m.group(1)

                            nameScene, ok = QtGui.QInputDialog.getText (self, "Enter a name for %s" % base, "Name for %s :" % base, QtGui.QLineEdit.Normal, base.replace("_","-").replace(" ", "-"))
                            if "_" in nameScene:
                                nameScene = nameScene.replace("_", "-")
                            if nameScene == "" and template_path.is_optional("name") == False:
                                self._overlay.show_error_message("Name is mandatory")
                                return
                            if nameScene != "":
                                fields["name"] = nameScene

                        elif "grp_name" in template_path.keys:
                            exp = "(.+)_[Vv]*\d+"
                            m = re.search(exp, base)
                            if m:
                                base = m.group(1)

                            nameScene, ok = QtGui.QInputDialog.getText (self, "Enter a grp_name for %s" % base, "grp_name for %s :" % base, QtGui.QLineEdit.Normal, base.replace("_","-").replace(" ", "-"))
                            if "_" in nameScene:
                                nameScene = nameScene.replace("_", "-")
                            if nameScene == "" and template_path.is_optional("grp_name") == False:
                                self._overlay.show_error_message("Name is mandatory")
                                return
                            if nameScene != "":
                                fields["grp_name"] = nameScene
                                


                        fields["Step"] = stepShortName
                        
                        version = 0
                        print fields

                        publishedFiles = tk.paths_from_template(template_path, fields, ["version"], skip_missing_optional_keys=True) 
                        print publishedFiles
                        for publishedFile in publishedFiles:
                            fields_file = template_path.get_fields(publishedFile)
                            if "version" in fields_file: 
                                if fields_file["version"] > version:
                                    version = fields_file["version"]

                        fields["version"] = version + 1

                        print fields
                        if "udim" in fields:
                            template_path = tk.templates['asset_publish_area_textures_udim']

                        destPath = template_path.apply_fields(fields)
                        print destPath

                        # creating the path if it doesn't exists.
                        if not os.path.exists(os.path.dirname(destPath)): 
                            os.makedirs(os.path.dirname(destPath))



                        thumbnail = None
                        convertionLine = None
                        thumbnailGenerator = None
                        if path.endswith(".abc"):
                            tank_type = "Alembic %s" % fields["Step"]
                            #convertionLine = "//server01/shared/sharedShotgun/abcconvert.exe -force -toOgawa %s %s" % (path, destPath)
                            thumbnail = path.replace(".abc", ".jpg")
                        elif path.endswith(".obj"):
                            tank_type = "Alembic %s" % fields["Step"]
                            convertionLine = "//server01/shared/sharedShotgun/WFObjConvert_obj2abc.exe %s %s" % (path, destPath)
                            thumbnail = path.replace(".obj", ".jpg")                    
                        elif path.endswith(".mb") or path.endswith(".ma"):
                            tank_type = "Maya %s" % fields["Step"]
                        elif ext in imgExtension:
                            if ext != ".tx":
                                convertionLine = "//VSERVER01/RoyalRender6/render_apps/renderer_plugins/maya/win_x64/2013/modules/mtoa-1.0.0/bin/maketx.exe -o %s -u --oiio %s" % (destPath, path)
                            
                            if entityType == "HDRi":
                                tank_type = "HDRi" 
                            else:
                                tank_type = "Texture" 

                            thumbnail = destPath.replace(".tx", ".jpg")
                            thumbnailGenerator = "//VAPPS/Apps/ImageMagick-6.8.9-Q16\convert.exe -resize 1024 %s[0] %s" % (destPath, thumbnail)



                            
                        if convertionLine:
                            os.system(convertionLine)
                        else:
                            shutil.copyfile(path, destPath)

                        if thumbnailGenerator:
                            if entityType != "HDRi":
                                os.system(thumbnailGenerator)
                            else:
                                tmpSource = destPath.replace(".tx", "_temp16bits.tx")
                                print tmpSource
                                tmpSourceGen = "//VSERVER01/RoyalRender6/render_apps/renderer_plugins/maya/win_x64/2013/modules/mtoa-1.0.0/bin/maketx.exe -o %s -d uint16 -u --oiio %s" % (tmpSource, destPath)
                                os.system(tmpSourceGen)
                                print tmpSourceGen
                                thumbnailGenerator = "//VAPPS/Apps/ImageMagick-6.8.9-Q16\convert.exe -gamma 2.2 -resize 1024 %s[0] %s" % (tmpSource, thumbnail)
                                print thumbnailGenerator
                                os.system(thumbnailGenerator)
                                os.remove(tmpSource)
                                    
                                

                        #ALTERING DESTPATH FOR SEQUENCE
                        if ext in imgExtension:
                            if "udim" in fields:

                                fields["udim"] = "FORMAT: #" 
                                destPath = template_path.apply_fields(fields)
                                if len(tank.util.find_publish(tk, [destPath])) > 0:
                                    # check if we must publish
                                    publishing = False                      

                                


                        # get all the assets for the project
                        if "name" in fields:
                            name = "%s_%s_%s" % (fields["Asset"], fields["name"], fields["Step"])
                        elif "grp_name" in fields :
                            name = "%s_%s_%s" % (fields["Asset"], fields["grp_name"], fields["Step"])
                        else:
                            name = "%s_%s" % (fields["Asset"], fields["Step"])

                        args = {
                            "tk": tk,
                            "context": ctx,
                            "comment": "",
                            "path": destPath,
                            "name": name,
                            "thumbnail_path": thumbnail,
                            "version_number": fields["version"],
                            "published_file_type":tank_type,
                        }
                        
                        print args

                        if publishing:
                            toPublish.append(args)
                            

                            # we must create a work file too
                            if work_template_path:
                                fields["version"] = fields["version"] + 1
                                destPathWork = work_template_path.apply_fields(fields)                      
                                shutil.copyfile(path, destPathWork)



                for args in toPublish:
                    sgtk.util.register_publish(**args)            

            self._overlay.hide()
            self._overlay.show_message("Publishes successful")


        except Exception, e:
           self._overlay.show_error_message("An error was reported: %s" % e)


class AppDialog(QtGui.QWidget):
    """
    Main application dialog window
    """
    
    def __init__(self):
        """
        Constructor
        """
        # first, call the base class and let it do its thing.
        QtGui.QWidget.__init__(self)
        


        # now load in the UI that was created in the UI designer
        self.ui = Ui_Dialog() 
        self.ui.setupUi(self)
        
        #################################################
        # maintain a list where we keep a reference to
        # all the dynamic UI we create. This is to make
        # the GC happy.
        self._dynamic_widgets = []

        # most of the useful accessors are available through the Application class instance
        # it is often handy to keep a reference to this. You can get it via the following method:
        app = sgtk.platform.current_bundle()

        tab = self.ui.frame
        

        layout = QtGui.QVBoxLayout(tab) 
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)         

       
        view = QtGui.QTreeView(tab)
        layout.addWidget(view)

        # a horiz layout to host search
        hlayout = QtGui.QHBoxLayout()
        layout.addLayout(hlayout)        

        # add search textfield
        search = QtGui.QLineEdit(tab)
        search.setStyleSheet("QLineEdit{ border-width: 1px; "
                                    "background-image: url(:/res/search.png);"
                                    "background-repeat: no-repeat;"
                                    "background-position: center left;"
                                    "border-radius: 5px; "
                                    "padding-left:20px;"
                                    "margin:4px;"
                                    "height:22px;"
                                    "}")
        search.setToolTip("Use the <i>search</i> field to narrow down the items displayed in the tree above.")
        try:
            # this was introduced in qt 4.7, so try to use it if we can... :)
            search.setPlaceholderText("Search...")
        except:
            pass

        hlayout.addWidget(search) 


        # and add a cancel search button, disabled by default
        clear_search = QtGui.QToolButton(tab)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/res/clear_search.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        clear_search.setIcon(icon)
        clear_search.setAutoRaise(True)
        clear_search.clicked.connect( lambda editor=search: editor.setText("") )
        clear_search.setToolTip("Click to clear your current search.")
        hlayout.addWidget(clear_search)

        # set up data backend  

        filters = [
            ["project", "is", app.context.project], 
                # ["step", "in", 
                #     [
                #         {'code': 'Art', 'entity_type': 'Asset', 'id': 9, 'type': 'Step'},
                #         {'code': 'Model', 'entity_type': 'Asset', 'id': 10, 'type': 'Step'},
                #         {'code': 'Rig', 'entity_type': 'Asset', 'id': 11, 'type': 'Step'},
                #         {'code': 'Rendering', 'entity_type': 'Asset', 'id': 12, 'type': 'Step'},
                #         {'code': 'Grooming', 'entity_type': 'Asset', 'id': 14, 'type': 'Step'},
                #         {'code': 'texturing', 'entity_type': 'Asset', 'id': 47, 'type': 'Step'},
                #         {'code': 'Simulation', 'entity_type': 'Asset', 'id': 48, 'type': 'Step'}
                #     ]
                # ]
            ]

        sg_entity_type = "Task"
        model = SgEntityModel(self, view, sg_entity_type, filters, ["entity", "content"])

        # set up right click menu
        action_ea = QtGui.QAction("Expand All Folders", view)
        action_ca = QtGui.QAction("Collapse All Folders", view)
        action_refresh = QtGui.QAction("Refresh", view)

        action_ea.triggered.connect(view.expandAll)
        action_ca.triggered.connect(view.collapseAll)
        action_refresh.triggered.connect(model.async_refresh)
        view.addAction(action_ea)
        view.addAction(action_ca)
        view.addAction(action_refresh)
        view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)


        # make sure we keep a handle to all the new objects
        # otherwise the GC may not work
        self._dynamic_widgets.extend( [tab,
                                       layout,
                                       hlayout,
                                       search,
                                       clear_search,
                                       view,
                                       action_ea,
                                       action_ca,
                                       action_refresh] )

        # set up proxy model that we connect our search to
        proxy_model = SgEntityProxyModel(self)
        proxy_model.setSourceModel(model)
        search.textChanged.connect(lambda text, v=view, pm=proxy_model: self._on_search_text_changed(text, v, pm) ) 

        # configure the view
        view.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        view.setProperty("showDropIndicator", False)
        view.setIconSize(QtCore.QSize(20, 20))
        view.setStyleSheet("QTreeView::item { padding: 6px;  }")
        view.setUniformRowHeights(True)
        view.setHeaderHidden(True)
        view.setModel(proxy_model) 


        # by first creating a direct handle to the selection model before
        # setting up signal / slots
        selection_model = view.selectionModel()
        self._dynamic_widgets.append(selection_model)
        #selection_model.selectionChanged.connect(self._on_treeview_item_selected)


        # finally store all these objects keyed by the caption
        self.ep = EntityPreset(sg_entity_type, 
                          model, 
                          proxy_model, 
                          view)
        # ctx = sgtk.platform.current_bundle().context
        #  ctx

        # DROP AREA
        self.dropArea = DropWidget(self)
        self.ui.horizontalLayout.addWidget(self.dropArea)

        model.async_refresh()


    def _get_selected_entity(self):
        """
        Returns the item currently selected in the tree view, None
        if no selection has been made.
        """

        selected_item = None
        selection_model = self.ep.view.selectionModel()
        if selection_model.hasSelection():

            current_idx = selection_model.selection().indexes()[0]

            model = current_idx.model()

            if not isinstance( model, SgEntityModel ):
                # proxy model!
                current_idx = model.mapToSource(current_idx)

            # now we have arrived at our model derived from StandardItemModel
            # so let's retrieve the standarditem object associated with the index
            selected_item = current_idx.model().itemFromIndex(current_idx)

        return selected_item        
        
    def _on_search_text_changed(self, pattern, tree_view, proxy_model):
        """
        Triggered when the text in a search editor changes.

        :param pattern: new contents of search box
        :param tree_view: associated tree view.
        :param proxy_model: associated proxy model
        """

        # tell proxy model to reevaulate itself given the new pattern.
        proxy_model.setFilterFixedString(pattern)

        # change UI decorations based on new pattern.
        if pattern and len(pattern) > 0:
            # indicate with a blue border that a search is active
            tree_view.setStyleSheet("""QTreeView { border-width: 3px;
                                                   border-style: solid;
                                                   border-color: #2C93E2; }
                                       QTreeView::item { padding: 6px; }
                                    """)
            # expand all nodes in the tree
            tree_view.expandAll()
        else:
            # revert to default style sheet
            tree_view.setStyleSheet("QTreeView::item { padding: 6px; }")

    def closeEvent(self, event):
        """
        Executed when the main dialog is closed.
        All worker threads and other things which need a proper shutdown
        need to be called here.
        """
        # display exit splash screen
        splash_pix = QtGui.QPixmap(":/res/exit_splash.png")
        splash = QtGui.QSplashScreen(splash_pix, QtCore.Qt.WindowStaysOnTopHint)
        splash.setMask(splash_pix.mask())
        splash.show()
        QtCore.QCoreApplication.processEvents()

        self.ep.model.destroy()

        # close splash
        splash.close()

        # okay to close dialog
        event.accept()            

class EntityPreset(object):
    """
    Little struct that represents one of the tabs / presets in the
    Left hand side entity tree view
    """
    def __init__(self, entity_type, model, proxy_model, view):
        self.model = model
        self.proxy_model = proxy_model
        self.view = view
        self.entity_type = entity_type 
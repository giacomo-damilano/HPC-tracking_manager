#!/bin/bash

#########################################################################################
#                                  Default Variables                                    #
#########################################################################################

DIR=$PWD
SFILE="$HOME/bin/.rng"
PFILE="$HOME/bin/.presets"
WLOG="$HOME/bin/.wlog"
WLOGf="$HOME/bin/.wulog"
CUE="pqph"
CORE=12
MEM=47988
WALLT="119:59:00"
QUIET=1
FRC=0
CORRECTION=1
RED='\033[0;31m'
NC='\033[m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
OPT=0

#########################################################################################
#                                  Debugging Function                                   #
#########################################################################################

debug(){
	echo "1.PWD	 $PWD"
	echo "2.#	 $#"
	echo "3.*	 $*"
	echo "4.OPTARG	 ${OPTARG}"
	echo "5.OPTIND	 ${OPTIND}"
	echo "6.CUE   	 ${CUE}"
	echo "7.CORE  	 ${CORE}"
	echo "8.MEM   	 ${MEM}"
	echo "9.WALLTIME ${WALLT}"
	echo "10.MAXDISK ${MAXDISK}"
}

#########################################################################################
#                                   Help output                                         #
#########################################################################################

usage(){
    echo -e "gaussian function v1.2

${RED}NAME${NC}
        gfunc


${RED}SYNOPSIS${NC}
        gf [jobfilename.com]


${RED}OPTIONS${NC}
        ${BLUE}-q${NC} [cue]
                set the cue for the job, default is pqph
        ${BLUE}-c${NC} [cores]
                sets the number of cores, 8 is set as default
        ${BLUE}-m${NC} [memory]
                sets the quantity of memory to use (MB or GB)
        ${BLUE}-w${NC} [walltime]
                set the walltime
        ${BLUE}-g${NC} [gaussian version]
                sets the version of gaussian in use (e.g. d01)
        ${BLUE}-s${NC} silent
                send directly the job
        ${BLUE}-p${NC} [preset]
                preset =
			[0-9]	load a preset
			show	list the saved preset
			set	open the editor to set the preset
        ${BLUE}-d${NC} [max disk]
                set the maxdisk
        ${BLUE}-n${NC} no correction
                no correction of the input file
        ${BLUE}-l${NC} [select]
		select =
			all
			work ID (e.g. '7197851')
		prints the log of the jobs sent
        ${BLUE}-h${NC}
		help

${RED}DESCRIPTION${NC}
This function sends the jobs to the HPC.
It also corrects the settings of your file automatically.
In the input file the checkpoint filename is set equally to the input filename, the number of cores is set coherently to the input as the memory. This automatic correction can be disabled by -n option
This function relies on a modified version of a script files given me by Claire (thanks Claire) that have to be placed in  ~/bin.
Next function that is projected to be added is the correction of the input file settings even if they are not written at all in the input file.
Enjoy!!"
}

bytechunker(){
	local __resultvar=${1}
	if [[ ${1} =~ .*"MB" ]];
	then
		local MBYTES=${1%MB};
		elif [[ $1 =~ .*"GB" ]]
	then
		local MBYTES=${1%GB};
		let "MBYTES=MBYTES*1000";
	else
		local MBYTES=${1-"800000"};
	fi
	echo $MBYTES;

    	eval $__resultvar="'$MBYTES'"
}

#########################################################################################
#         Creating/Verifing the existence of some files used by the function            #
#########################################################################################

if [[ ! -d ~/bin ]]
then
        mkdir ~/bin
fi

if [[ ! -f ${SFILE} ]]
then
	echo '#!/bin/sh

# submit jobs to the que with this script using the following command:
# rng4 is this script
# jobname is a name you will see in the qstat command
# name is the actual file minus .com etc it is passed into this script as ${in%.com}
#
# qsub rng -N jobname -v in=name

# batch processing commands
#PBS -l walltime=119:59:00
#PBS -lselect=1:ncpus=12:mem=48000MB:tmpspace=400gb
#PBS -j oe
#PBS -q pqph
#PBS -m ae

# load modules
#
module load gaussian/g09-d01

# check for a checkpoint file
#
# variable PBS_O_WORKDIR=directory from which the job was submited.
   test -r $PBS_O_WORKDIR/${in%.com}.chk
   if [ $? -eq 0 ]
   then
     echo "located $PBS_O_WORKDIR/${in%.com}.chk"
     cp $PBS_O_WORKDIR/${in%.com}.chk $TMPDIR/.
   else
     echo "no checkpoint file $PBS_O_WORKDIR/${in%.com}.chk"
   fi
#
# run gaussian
#
  g09 $PBS_O_WORKDIR/${in}
  cp $TMPDIR/${in%.com}.chk /$PBS_O_WORKDIR/.
  cp $TMPDIR/${in%.com}.wfx /$PBS_O_WORKDIR/.
#  cp *.chk /$PBS_O_WORKDIR/pbs_${in%.com}.chk
#  test -r $TMPDIR/fort.7
#  if [ $? -eq 0 ]
#  then
#    cp $TMPDIR/fort.7 /$PBS_O_WORKDIR/${in%.com}.mos
#  fi
# exit' > "${SFILE}"
        chmod a+x "${SFILE}"
fi

if [[ ! -f ${PFILE} ]]
then
	echo '##	 Here is where to list the preset for gaussian calculations
##	 Each line is a preset and it is written in this way :
##		 [CUE];[CORES];[MEMORY];[WALLTIME];[GAUSSIAN VERSION];[MAXDISK]
##	e.g	pqph;8;14400MB;119:59:00;d01;800GB
##
##
##-----------------------------------------------------------------------------
##
##	presets starts from next line
pqph;12;48000MB;119:59:00;d01;400GB' > "${PFILE}"
fi

#########################################################################################
#                              Retriving inputted options                               #
#########################################################################################

while getopts fhnsc:d:g:l:m:p:q:w: OPTION
do
	if [[ $OPT -lt $OPTIND ]]
	then
		let "OPT=OPTIND - 1"
	fi

        case $OPTION in
        d)
                if [[ $OPTARG =~ .*"MB" ]];
                then
                        MAXDISK=${OPTARG%MB};
                elif [[ $OPTARG =~ .*"GB" ]]
                then
                        MAXDISK=${OPTARG%GB};
                        let "MAXDISK=MAXDISK*1000";
                else
                        MAXDISK=${OPTARG-"16000"};
                fi
		;;
	p)
		if [[ $OPTARG =~ [0-99] ]]
		then
			i=0;
			while read VAR
			do
				let "m=i-9"
				if [[ $m == $OPTARG ]]
				then
					echo $VAR
					IFS=";" read -ra PRESET <<< "$VAR"
					CUE=${PRESET[0]};
					CORE=${PRESET[1]};

                			if [[ ${PRESET[2]} =~ .*"MB" ]];
		                	then
        			                MEM=${PRESET[2]%MB};
			                elif [[ ${PRESET[2]} =~ .*"GB" ]]
	        		        then
						$MEM=${PRESET[2]%GB}
                			        let "MEM=MEM*1000";
		        	        else
        			                MEM=${PRESET[2]-"16000"};
	        	        	fi
					WALLT=${PRESET[3]};
					GAUSS=${PRESET[4]};
                			if [[ ${PRESET[5]} =~ .*"MB" ]];
		                	then
        			                MAXDISK=${PRESET[5]%MB};
			                elif [[ ${PRESET[5]} =~ .*"GB" ]]
	        		        then
                			        MAXDISK=${PRESET[5]%GB};
        			                let "MAXDISK=MAXDISK*1000";
		        	        else
        			                MAXDISK=${PRESET[5]-"16000"};
	        	        	fi
				fi
				((i++))
			done < $PFILE;
		elif [[ $OPTARG == "show" ]]
		then
			i=1;
			while read VAR
			do
				if [[ $i -gt 9 ]]
				then
					IFS=";" read -ra PRESET <<< "$VAR"
					let "m=i-9"
					echo "$m - cue: ${PRESET[0]} cores:${PRESET[1]} memory: ${PRESET[2]} walltime: ${PRESET[3]} gaussian version: ${PRESET[4]} max disk: ${PRESET[5]}";
				fi
				((i++))
			done < $PFILE
			exit
		elif [[ $OPTARG == "set" ]]
		then
			vi $PFILE
			exit
		fi
		WHITESTRIPES="Charged preset : $CUE $CORE $MEM $WALLT $GAUSS $MAXDISK";
		;;
	h)
                usage;
                exit;
                ;;
        q)
                CUE=${OPTARG-"pqph"};
		;;
        c)
                CORE=${OPTARG-"8"};
		;;
        f)
                FRC=1;
		;;
        m)
                if [[ $OPTARG =~ .*"MB" ]];
                then
                        MEM=${OPTARG%MB};
                elif [[ $OPTARG =~ .*"GB" ]]
                then
                        MEM=${OPTARG%GB};
                        let "MEM=MEM*1000";
                else
                        MEM=${OPTARG-"16000"};
                fi
                ;;
        n)
                CORRECTION=0;
                ;;
        g)
                GAUSS=${OPTARG};
                ;;
        w)
                WALLT=${OPTARG};
                ;;
        s)
                QUIET=1;
		;;
	l)
		if [[ ${OPTARG} == 'all' ]]
		then
			cat $WLOG;
		else
			sed -n "/${OPTARG}/p" $WLOG;
		fi
		;;
        ?)
                usage;
                exit;
                ;;
        esac
done

if [[ $# -eq 0 ]]
then
        usage
        exit
fi

shift $OPT

if [[ ! -f $GAUSS && -f "${GAUSS}.com" ]]
then
	$GAUSS="${GAUSS}.com"
fi


#########################################################################################
#                             Correcting the script file                                #
#########################################################################################
if [[ -n $MAXDISK ]]
then
	sed -i "s/#PBS -lselect=1:ncpus=.*/#PBS -lselect=1:ncpus=${CORE}:mem=${MEM}MB:tmpspace=${MAXDISK}MB/" ${SFILE}
else
	sed -i "s/#PBS -lselect=1:ncpus=.*/#PBS -lselect=1:ncpus=${CORE}:mem=${MEM}MB/" ${SFILE}
fi
sed -i "s/#PBS -l walltime=.*/#PBS -l walltime=${WALLT}/" ${SFILE}

if [ "$CUE" != "PUBLIC" ]
then
	grep -q "#PBS -q .*" ${SFILE} && sed -i "s/#PBS -q .*/#PBS -q ${CUE}/" "${SFILE}" || sed -i "14s/^/#PBS -q ${CUE}\n/" ${SFILE}
else
	grep -q "#PBS -q .*" ${SFILE} && sed -i "/#PBS -q .*/d" ${SFILE}
fi

if [[ -n $GAUSS ]]
then
        sed -i "s/module load gaussian\/g09-.*/module load gaussian\/g09-${GAUSS}/" ${SFILE}
fi

#########################################################################################
#                             Pushing the job to the HPC                                #
#########################################################################################

while [ $# -gt 0 ]
do

	if [[ ! -f ${1} && -f "${1}.com" ]]
	then
		set -- "${1}.com"
	fi

        NMFL=${1%.com}

	if [[ ! -f ${1} ]]
        then
                echo "\"${1}\" does not exists."
                exit
        elif [[ ! ${1} =~ .*'.com' ]]
        then
                echo "\"${1}\" is not a com file."
                exit
        fi

        if [[ $CORRECTION -eq 1 ]]
        then
		CD=$(pwd)
		CD=${CD//\//\\\/}'\/'
                GMEM=$((${MEM} * 15 / 20))
                gmem=$(grep -i -c "%mem=.*/" ${1})
                gpshar=$(grep -i -c "%nprocshared=.*/" ${1})
                gchk=$(grep -i -c "%chk=./" ${1})
		echo $gmem $gpshar $gchk
		grep -q "%mem=" ${1} && sed -i "s/%mem=.*/%mem=${GMEM}MB/" ${1} || sed -i "1s/^/%mem=${GMEM}MB\n/" ${1}
                grep -q "%nprocshared=" ${1} && sed -i "s/%nprocshared=.*/%nprocshared=${CORE}/" ${1} || sed -i "1s/^/%nprocshared=${CORE}\n/" ${1}
		sed -i "s/%chk=.*chk/%chk=${1%com}chk/" ${1}
              # sed -i "s/%chk=.*chk/%chk=$CD${1%com}chk/" ${1}
		if [[ -n $MAXDISK ]]
		then
                	sed -i "s/maxdisk=.*B/maxdisk=${MAXDISK}MB/" ${1}
		fi
        fi

        if [[ $QUIET -eq 1 ]]
        then
                response="y"
	else
                echo -e "${RED}--------------------------------------------------------------------------------\n\n${NC}"
                more ${1}
                echo -e "${RED}--------------------------------------------------------------------------------\n\n${NC}"
                echo -e $YELLOW$WHITESTRIPES$NC
		echo -e "qsub -N ${NMFL:0:15} -v in=${1}  ~/bin/.rng"
                echo "Cores: $CORE; Memory: $MEM; Cue: $CUE; Walltime: $WALLT; Gaussian-version: $GAUSS; Maxdisk: $MAXDISK"
                echo -e "${RED}------------------------------Are you sure? [y/N]-------------------------------${NC}"
                read -r -p " " response
        fi

        if [[ $response =~ ^([yY][eE][sS]|[yY])$ ]]
        then
		if [[ $FRC=1 ]]
		then
			out=$(qsub -p 100 -N${NMFL:0:15} -v in=${1%.com} ~/bin/.rng);
		else
			out=$(qsub -N "${NMFL:0:15}" -v in="${1%.com}" ~/bin/.rng);
		fi
		cp="$(pwd)"
		if [[ -n $out ]]
		then
		echo "$(date -u +'%d/%m - %H:%M') | $out | $NMFL | ${cp#/work/gd2613/jobs/}" >> $WLOG
		echo "$(date -u +'%d/%m - %H:%M') | $out | $NMFL | ${cp#/work/gd2613/jobs/}" >> $WLOGf
		fi
		echo $out
                echo -e "${YELLOW}\n $(date -u +'%H:%M') - Work sent \n${NC}"
        else
                echo -e "${YELLOW}\n Work aborted \n${NC}"
        fi

        shift
done
